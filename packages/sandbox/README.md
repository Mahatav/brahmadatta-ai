# packages/sandbox — subprocess jail (#81)

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
| A file-size limit is reported as `FILE_SIZE`, not `NONE` (SEC-35) | `test_file_size_limit_is_reported_as_file_size_not_none` |
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
3. Sweeps the pre-kill snapshot (plus a fresh walk, to catch anything forked during the
   grace period) and `SIGKILL`s each surviving pid directly, by pid, independent of
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
