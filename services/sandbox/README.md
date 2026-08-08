# services/sandbox — subprocess jail (#81)

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
pytest services/sandbox/tests -q
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
| Output is capped rather than buffered without limit | `test_output_is_capped` |
| Cleanup runs on success, on failure, and on cancel | `test_cleanup_on_success`, `test_cleanup_on_failure`, `test_cleanup_on_cancel` |
| Cancel from another thread stops a running command | `test_cancel_stops_a_running_command_from_another_thread` |
| A populated build tree is still cleaned up | `test_the_build_leaves_nothing_behind` |
| The environment is scrubbed to an allowlist | `test_environment_is_scrubbed_to_the_allowlist` |
| A jailed run reports `SUBPROCESS_JAIL`, never the container mode | `test_result_reports_the_isolation_mode_honestly` |
| The real demo target configures, builds and passes 8/8 ctest inside it | `test_demo_target_configures_builds_and_tests_inside_the_jail` |

### Memory is enforced on Linux and not on macOS

`RLIMIT_AS` is set, and on Linux it works: `test_memory_limit_stops_an_allocator` passes
in a `python:3.12-slim` container.

On **Darwin it does not**. `setrlimit(RLIMIT_AS, ...)` is refused, the child reports an
unlimited address space, and a 64 MiB policy allowed a 900 MB allocation. That was
measured, not assumed. The test is `skipif`-ed on Darwin with that reason attached rather
than deleted.

Do not take either on trust:

```python
from services.sandbox import probe_limits
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
- **`PATH` is inherited**, because a build needs a compiler. It is the largest hole in the
  environment scrubbing and it is deliberate.

## Using it

```python
from services.sandbox import Jail, JailPolicy

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
number when it cannot produce a real one.

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
