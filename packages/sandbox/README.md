# packages/sandbox — subprocess jail (#81) and container isolation (#15)

A working-directory jail, resource limits, and a hard timeout that kills the whole
process group. Enough to build and test the demo target for the D3 gate.

## This is not sufficient for fuzzing untrusted code

Stated first because it is the reason this issue was allowed to exist separately from
#15.

A jailed command runs **as the same user, on the same filesystem, with the same network,
in the same kernel namespaces** as the orchestrator. A process started here can read the
operator's home directory, open a socket to anywhere, and write to any path the operator
can write to. Nothing in this package prevents any of that, and nothing in this package
claims to.

**Fuzzing untrusted code requires #15 — rootless container isolation — and #15 must land
before #28 runs on D4.** The CTO split #81 out of #15 (§2.4) because the D3 gate needs a
build and a test run, not container isolation, and blocking the first gate on a full day
of Podman work costs a day for nothing. That is the entire justification for the split,
and it holds only as long as nothing untrusted runs in here.

`IsolationMode.SUBPROCESS_JAIL` exists in the frozen contract so a run contained this way
cannot be reported as the container path. `docs/09-company/10-fallback-ladder.md` C1 says
the same thing from the other direction: a finale in #81 mode is a finale with no live
fuzz campaign in it.

## What it does enforce

Every row is claimed because a named test demonstrates it. Run them:

```sh
pytest packages/sandbox/tests -q
```

| Property | Demonstrated by |
|---|---|
| A command runs in the jail root | `test_command_runs_in_the_jail_root` |
| A path outside the jail is refused before the command runs | `test_path_outside_the_jail_is_refused` |
| A symlink pointing out of the jail is refused | `test_symlink_escape_is_refused` |
| A `cwd` outside the jail is refused | `test_running_with_a_cwd_outside_the_jail_is_refused` |
| A CPU budget stops a spinner, reported as `CPU` not as a bare signal | `test_cpu_limit_stops_a_spinner` |
| A wall-clock timeout fires and is reported, not hung | `test_wall_clock_timeout_is_reported_not_hung` |
| The timeout kills grandchildren — no orphans | `test_timeout_kills_grandchildren_leaving_no_orphans` |
| The timeout kills a grandchild that detached via `setsid()` (SEC-33, Linux) | `test_timeout_kills_a_grandchild_that_detaches_via_setsid` |
| The sweep catches every descendant of rapid, repeated fork-and-detach, not just the ones present at the pre-kill snapshot (SEC-38, Linux) | `test_sweep_catches_rapid_repeated_detachment` |
| A file-size limit is reported as `FILE_SIZE`, not `NONE` (SEC-35) | `test_file_size_limit_is_reported_as_file_size_not_none` |
| `FILE_SIZE` is still reported for a target whose `SIGXFSZ` disposition is `SIG_IGN`, e.g. CPython (SEC-35, residual gap) | `test_file_size_limit_is_reported_for_a_target_that_ignores_sigxfsz` |
| Output is capped rather than buffered without limit | `test_output_is_capped` |
| Cleanup runs on success, on failure, and on cancel | `test_cleanup_on_success`, `test_cleanup_on_failure`, `test_cleanup_on_cancel` |
| Cancel from another thread stops a running command | `test_cancel_stops_a_running_command_from_another_thread` |
| A populated build tree is still cleaned up | `test_the_build_leaves_nothing_behind` |
| The environment is scrubbed to an allowlist | `test_environment_is_scrubbed_to_the_allowlist` |
| A jailed run reports `SUBPROCESS_JAIL`, never the container mode | `test_result_reports_the_isolation_mode_honestly` |
| The real demo target configures, builds and passes 8/8 ctest inside it | `test_demo_target_configures_builds_and_tests_inside_the_jail` |
| `limits_applied` is a real per-run measurement, not a platform guess | `test_limits_applied_is_a_real_per_run_measurement` |
| `limits_applied` agrees with `probe_limits()` on this kernel | `test_limits_applied_agrees_with_probe_limits_on_memory` |
| `limits_applied` is captured even for a command killed immediately | `test_limits_applied_survives_a_command_that_is_immediately_killed` |

### `limits_applied` — a per-run record, not a platform guess (D-054)

`JailResult.limits_applied` answers "did *this run* have the protection it claims to
have", for the two limits that can be silently refused: `memory_bytes` (`RLIMIT_AS`) and
`max_processes` (`RLIMIT_NPROC`). It is populated from the real outcome of each
`setrlimit()` call made inside the child, before it execs — never inferred from
`sys.platform`.

The mechanism, because it crosses a fork: a pipe is opened before the child forks; inside
`preexec_fn` — which runs after `fork()` but before `exec()`, the only window where Python
code in the child still exists — each `setrlimit()` call is wrapped in its own
`try`/`except`, the outcome recorded, and the resulting `{"memory_bytes": bool,
"max_processes": bool}` written to the pipe and the write end closed before `exec()`
replaces the process image. The parent reads it back once `Popen()` returns.

This is deliberately not the same thing as `probe_limits()`. That function is a
standalone, ahead-of-any-mission diagnostic: it runs synthetic programs that try to
*exceed* each limit and observes whether behaviour actually changed. `limits_applied` is
the per-run, after-the-fact record of whether the `setrlimit` call itself succeeded for
*this* command. They ask different questions and `test_limits_applied_agrees_with_probe_limits_on_memory`
checks that, on this kernel, they agree.

### A detached grandchild does not escape the timeout (SEC-33)

`killpg()` only reaches processes still in the child's process group. A process that
calls `os.setsid()` — deliberately, to survive its parent, or as a side effect of a
daemonizing library a fuzz target happens to link against — starts a **new** session and
process group and is invisible to `killpg()` from that instant on, while remaining, in
every other sense the kernel tracks, this process's descendant.

`cybersecurity`'s review of this package found it, reproduced it directly (a detached
grandchild confirmed alive, still running, after full teardown), and it mattered more
than an ordinary finding: the CTO's D-053 ruling cited `test_timeout_kills_grandchildren_leaving_no_orphans`
— "no orphans" — as the decisive reason this implementation won over a rival one, and
that test covered only the cooperative case.

The fix does not need process groups at all. `setsid()` changes a process's session and
process group id; it cannot and does not change its **parent** process id — that is
fixed by the kernel at fork time and survives detachment intact. So `_kill_group`:

1. Walks `/proc` by parent id and **snapshots** every descendant of the jailed process
   *before* touching anything. This ordering is load-bearing, not incidental: once the
   direct child dies and is reaped, a detached grandchild's parent-id link is gone too
   — the kernel reparents it to init (or whatever subreaper owns the pid namespace) the
   moment its recorded parent exits, and walking `/proc` *after* that finds nothing,
   because there is nothing left to find by that link.
2. Runs the ordinary `killpg()`-based SIGTERM-then-SIGKILL sequence, which still handles
   everything still in the process group — the common case, and cheaper than a full
   `/proc` walk for it.
3. Sweeps the pre-kill snapshot — expanded and re-frozen to a fixed point every pass, see
   SEC-38 below — and `SIGKILL`s each surviving pid directly, by pid, independent of
   whatever group or session it has put itself in.

This sweep is **Linux-only** (`/proc/*/stat`). That is the platform it is tested on and
the platform it needs to hold on — #81 exists for the D3 gate, which runs on the finale's
Linux stack. On another platform `_kill_group` is the process-group kill alone, and that
gap is stated here rather than narrowed silently.

**What it still does not catch:** a process that double-forks to reparent itself under
init directly, rather than merely calling `setsid()`. That changes the parent id itself,
not just the group — the exact link this fix depends on — and is a harder problem this
package does not claim to solve. It would need something closer to `PR_SET_CHILD_SUBREAPER`
on the orchestrator process itself, or a pid namespace, which starts to look like the
container boundary #15 exists for rather than a subprocess jail's job.

### The sweep catches rapid, repeated detachment, not just one (SEC-38)

The step-3 sweep above, as first shipped, combined the pre-kill snapshot with a *fresh*
`/proc` walk on every poll pass, rooted at the jailed process's own pid — meant to catch
anything a descendant forked after the snapshot was taken. It didn't work: by the time the
sweep runs, `_kill_group` has already signalled and (almost always) reaped that pid, so a
walk rooted at it finds nothing, for the sweep's entire remaining duration. Only pids the
snapshot happened to capture directly, by pid, ever got cleaned up — anything a *tracked*
descendant forked afterward, the exact shape of a target that detaches repeatedly instead
of once, had no path back to the dead root and was invisible every time, not occasionally.
`cybersecurity`'s review reproduced this directly, at the module's real default
`kill_grace_seconds=5.0`, under rapid repeated fork-and-detach.

Re-walking from every tracked pid each pass, not just the (normally dead) root, fixes most
of that — a tracked pid that's still alive has a correct, live link to whatever it forks
next. It is not sufficient on its own, though: killing a pid the instant it's discovered
races that pid's own next `fork()`, since the kernel does not order "deliver this fatal
signal" against "finish creating this child" — a `SIGKILL` sent on discovery can still let
one more fork complete, and that child is lost exactly as before, just one level further
down. A tighter poll interval only shrinks that window; it can't close it, because it
isn't a polling-frequency problem.

Closing it needs an extra step before anything is killed: every pid found alive is
`SIGSTOP`ped and *confirmed* stopped, not merely signalled (`_freeze`). A stopped process
cannot fork — its children up to that instant are fixed, permanently, since nothing here
ever sends `SIGCONT`. The discover-and-freeze cycle runs to a fixed point (a pass finds
nothing new, with everything currently tracked already frozen) before any `SIGKILL` is
sent, so nothing pending can still be mid-`fork()` at the moment it's finally killed.
`test_sweep_catches_rapid_repeated_detachment` chains many rapid fork-and-detach cycles at
the real default grace period and requires zero survivors across repeated runs — the
review's own bar: a single-detachment test does not demonstrate this.

**A residual, deliberately accepted gap in verification, not in the kill itself:** a
`SIGKILL`ed descendant that has already reparented away from this jail becomes a zombie
— a process-table entry awaiting `waitpid()` by whichever process now owns it — until
that process reaps it. This jail is not that process and cannot reap it; it can only
confirm the `SIGKILL` was delivered and the target is no longer *running* (checked via
`/proc/<pid>/stat`'s state field, which distinguishes a zombie from something still
consuming CPU or memory). A machine with a proper init or subreaper (`docker run --init`,
systemd, a normal shell) reaps it immediately and it disappears entirely, which is what
the production deployment gets. A bare process run directly as a container's PID 1 with
no reaper — the shape of the minimal test harness this bug was reproduced in — leaves it
as a zombie indefinitely. That is a process-table slot, not CPU or memory, and it is a
materially different failure than the one this fix closes.

### Memory is enforced on Linux and not on macOS

`RLIMIT_AS` is set, and on Linux it works: `test_memory_limit_stops_an_allocator` passes
in a `python:3.12-slim` container.

On **Darwin it does not**. `setrlimit(RLIMIT_AS, ...)` is refused, the child reports an
unlimited address space, and a 64 MiB policy allowed a 900 MB allocation. That was
measured, not assumed. The test is `skipif`-ed on Darwin with that reason attached rather
than deleted.

Do not take either on trust:

```python
from packages.sandbox import probe_limits
probe_limits()   # {'cpu_seconds': True, 'memory_bytes': ..., 'wall_clock_seconds': True}
```

`probe_limits()` runs a program that deliberately exceeds each limit and reports what the
kernel actually did. The finale runs on Linux, so the finale gets the memory ceiling; a
developer on a Mac does not, and should know it.

### Other limits that are weaker than they look

- **`RLIMIT_CPU` is per process, not per process group.** A command that forks gives each
  child its own budget. The wall clock is the only limit here that covers the whole group.
- **`RLIMIT_NPROC` is per user on most kernels**, so it is shared with everything else the
  operator is running. It is a brake on a fork bomb, not a defence against one.
- **`RLIMIT_FSIZE` bounds one file, not aggregate disk usage (SEC-36).** Twenty files at
  400 MiB each all individually stay under a 512 MiB `max_file_bytes` policy and still
  fill a disk this jail does not otherwise guard. Nothing here sums file sizes across a
  run. `test_file_size_limit_bounds_one_file_not_aggregate_usage` demonstrates the gap
  directly rather than leaving it as an unverified claim.
- **`PATH` is inherited**, because a build needs a compiler. It is the largest hole in the
  environment scrubbing and it is deliberate.

## Using it

```python
from packages.sandbox import Jail, JailPolicy

with Jail.create(JailPolicy(wall_clock_seconds=900)) as jail:
    shutil.copytree(source, jail.root / "src")

    configure = jail.run(["cmake", "-S", "src", "-B", "src/build"])
    build     = jail.run(["cmake", "--build", "src/build", "-j", "2"])
    tests     = jail.run(["ctest", "--test-dir", "src/build"])

    if not tests.ok:
        ...   # tests.limit_hit says whether it failed or was stopped
# the jail directory is gone here, on every path out
```

`JailResult` carries measured `wall_seconds`, `cpu_seconds` and `peak_memory_mb` — the
numbers `ResourceUsage` in the evidence bundle wants, and the ones the Core's resource
rail displays. They are measurements; there is nothing here that produces a plausible
number when it cannot produce a real one. `limits_applied` belongs in the evidence bundle
too, next to `isolation_mode`: a `SUBPROCESS_JAIL` run that could not actually set its
memory ceiling on this kernel should say so in the record, not just in a README.

`run(..., raise_on_limit=True)` turns a limit into `CpuExceededError`,
`WallClockExceededError` or `MemoryExceededError` instead of a result to branch on. Each
carries an `error_code` naming the `contracts.enums.ErrorCode` member the orchestrator
should surface, so a jail failure becomes a mission event without inventing vocabulary.

`JailPolicy.from_settings(settings.SANDBOX_POLICY)` maps the Django settings already in
`config/settings/base.py`. It ignores `runtime` and `network` on purpose: a subprocess
jail has no network namespace, so consuming `network: deny` would claim an isolation
property that is not delivered.

## Cancel

`jail.cancel()` is safe to call from another thread — which is the only way it is useful,
since the thread inside `run()` is blocked on the child. It SIGTERMs the process group,
waits out the grace period, SIGKILLs, and refuses any further commands. Leaving the
context manager cancels and cleans up whether the caller left normally or by exception.

---

# `container.py` — container isolation for untrusted target code (#15)

**This is the module #28's fuzzing worker runs inside.** `jail.py` above shares the
orchestrator's user, filesystem and network; `container.py` does not.

D-024 (`docs/09-company/08-security-review.md` §6) accepted a standard
(rootful-daemon) container — `--network none`, a fixed non-root uid, every
capability dropped, `no-new-privileges`, a read-only root filesystem, and
runtime-enforced resource caps — as the substitute for rootless Podman, under eight
binding conditions. **It is never described as "rootless"** (condition 8): the one
property it does not deliver is protection against a container-runtime escape
reaching host root. `contracts.enums.IsolationMode.CONTAINER_NO_NETWORK` [Δ #15] is
the honest name for a run in this mode; `ROOTLESS_CONTAINER` is reserved for a
genuine rootless run, which nothing in this codebase produces.

```python
from packages.sandbox.container import ContainerJail, ContainerJailPolicy

policy = ContainerJailPolicy(image="pinned-target-image@sha256:...")
with ContainerJail.create(policy, mission_ref=str(mission.id)) as sandbox:
    (sandbox.root / "seed.bin").write_bytes(seed)
    result = sandbox.run(["/usr/bin/fuzz-target", "/workspace/seed.bin"])
# the container and the host-side worktree are both gone here, on every path out
```

| D-024 condition | Enforced by | Proven by |
|---|---|---|
| 1. `--network none`, no exceptions | `ContainerJailPolicy.network` (fixed, `__post_init__` refuses any other value) | `test_dns_and_tcp_egress_both_fail` — an executed DNS lookup and a raw TCP connect from inside a running container, both asserted to fail |
| 2. `--user <uid>:<gid>`, never 0 | `ContainerJailPolicy.__post_init__` | `test_the_container_runs_as_a_fixed_non_root_user` — `id -u` run inside the container |
| 3. `--cap-drop ALL`, `no-new-privileges` | `_docker_run_args` | `test_docker_run_args_carry_every_flag_the_eight_conditions_require` |
| 4. Docker socket never bind-mounted | structural — the only `-v` this module ever emits is the worktree | `test_no_call_shape_can_mount_the_docker_socket` (this package) and `tests/architecture/test_container_isolation.py` (repo-wide) |
| 5. `--read-only` + sized tmpfs; worktree is the only writable mount | `_docker_run_args`, `ContainerJailPolicy.tmpfs_mb` | `test_the_root_filesystem_is_read_only`, `test_tmp_is_writable_scratch_under_the_read_only_root` |
| 6. `--memory`/`--cpus`/`--pids-limit`, wall-clock kill | `ContainerJailPolicy`, `ContainerJail.run` | `test_memory_limit_is_passed_to_the_runtime_and_enforced`, `test_wall_clock_timeout_is_reported_and_the_container_is_removed` |
| 7. Teardown + orphan reaper, on crash and cancel | `ContainerJail.close`/`cancel`, module-level `reap_orphans` | `test_cleanup_on_*`, `test_reap_orphans_removes_a_container_this_process_never_saw` |
| 8. Never called "rootless" | `IsolationMode.CONTAINER_NO_NETWORK` | code review — there is no test for a docstring, this is what one looks like |

## Why this module's teardown is simpler than `jail.py`'s

`jail.py`'s README (above) documents SEC-33 at length: a subprocess that calls
`os.setsid()` escapes the process group `killpg()` signals, because a subprocess
jail shares the orchestrator's PID namespace. A container has its **own** PID
namespace — `docker kill <name>` reaches the container's real PID 1, and the kernel
tears down every process inside that namespace when PID 1 dies. There is no
`setsid()`-style trick that gets a process out of its own PID namespace. This module
does not need `jail.py`'s `/proc`-walking snapshot-and-sweep at all.

## The worktree is `0o777`, not `0o700`

`jail.py`'s jail runs as the *same* uid as the orchestrator, so `0o700` is correct —
only the owner ever needs access. This container runs as a **different**, fixed uid
(`policy.uid`, default `10001`). A bind-mounted `0o700` directory owned by the
orchestrator's host uid is unwritable from inside the container — confirmed
directly (`Permission denied` writing into a `0700` mount from a non-owning uid).
World-writable is not a broader exposure here: the directory is created fresh per
`ContainerJail` with an unguessable `mkdtemp` name and removed in `close()`. The
isolation boundary is which *container* can reach it (exactly one, via the explicit
`-v` mount), not which local uid owns it.

## A macOS/colima gotcha, if you hit "permission denied" or empty files locally

Docker Desktop / colima's virtiofs mount only shares `$HOME` (and a short allowlist)
with the VM by default. A bind mount outside that set does not fail loudly — it
silently binds an **empty, root-owned directory** inside the container instead of
your actual files, which reads exactly like a permissions bug until you `ls -la`
both sides and notice the container never saw your files at all. Python's default
`tempfile.mkdtemp()` uses `/var/folders/...` on macOS, which is outside colima's
default share. `packages/sandbox/tests/test_container_jail.py` redirects
`tempfile.tempdir` under `$HOME` for exactly this reason — pass `parent=` to
`ContainerJail.create()` yourself if you hit this outside the test suite. Native
Linux (the finale's actual deployment target) has no such split.

## Using `reap_orphans` for real crash recovery

`ContainerJail.close()` — normal exit, failure, cancel — only runs from inside the
process that started the container. If the orchestrator itself is killed
(`SIGKILL`, OOM, a host crash) with a container still running, no Python code runs
to clean it up. Every container this module starts carries the label
`brahmadatta.sandbox=1` specifically so the *next* process to boot can find and
remove it:

```python
from packages.sandbox.container import reap_orphans

removed = reap_orphans()   # call once, early, at orchestrator startup
```

## What this module does not do

* Build the target image. The caller supplies an already-built, already-pinned
  `ContainerJailPolicy.image` — building one from a mission's source is a different
  concern (the compiler-toolchain-engineer's adapter).
* Require Podman. `ContainerJailPolicy.runtime` names the CLI binary (`"docker"` by
  default, matching D-024 and `SANDBOX_RUNTIME`'s default); anything that accepts
  the same `run`/`wait`/`stop`/`kill`/`logs`/`rm`/`inspect` subcommands works.
* Bound aggregate disk usage beyond the sized tmpfs — which, unlike `jail.py`'s
  `RLIMIT_FSIZE`, *is* a real ceiling the kernel refuses to exceed, not an advisory
  one bounding only a single file.
