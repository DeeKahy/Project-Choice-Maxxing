"""Concurrency / locking tests (#9).

Flask's test client is single-threaded, so we instead exercise the
locked CSV helpers directly from worker threads. The goal is to make sure
that a read-modify-write transaction wrapped in `csv_lock()` is serialized
even when many threads are racing on the same data.
"""
import threading


def test_concurrent_add_user_no_lost_writes(app_module):
    """20 threads each create a unique user. After they all finish, every
    user should be present (no lost writes from non-atomic CSV access)."""
    n = 20
    barrier = threading.Barrier(n)
    failures = []

    def worker(i):
        try:
            barrier.wait()
            ok = app_module.add_user(f"user{i:02d}", "passw0rd")
            if not ok:
                failures.append(("duplicate", i))
        except Exception as exc:  # noqa: BLE001
            failures.append((type(exc).__name__, str(exc)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert failures == [], f"unexpected failures: {failures}"

    # Seeded admin + n new users.
    users = app_module.get_users()
    usernames = sorted(u["username"] for u in users)
    expected = sorted(
        [app_module.ADMIN_USER] + [f"user{i:02d}" for i in range(n)]
    )
    assert usernames == expected


def test_concurrent_add_same_username_only_one_wins(app_module):
    """If 10 threads all try to add the same username, exactly one must
    succeed and the rest must report duplicate, with no exceptions."""
    n = 10
    barrier = threading.Barrier(n)
    successes = []
    duplicates = []
    errors = []

    def worker():
        try:
            barrier.wait()
            ok = app_module.add_user("racer", "passw0rd")
            (successes if ok else duplicates).append(threading.get_ident())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(successes) == 1
    assert len(duplicates) == n - 1
    assert app_module.get_user("racer") is not None
