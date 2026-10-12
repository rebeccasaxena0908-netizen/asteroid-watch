from pipeline.load import (APPROACH_COLUMNS, LoadCounts, split_counts, upsert_rows, upsert_sql)


def test_upsert_sql_updates_only_non_key_columns():
    sql = upsert_sql("t", ["id", "a", "b"], ["id"])
    assert sql == ("INSERT INTO t (id, a, b) VALUES (%s, %s, %s) "
                   "ON DUPLICATE KEY UPDATE a = VALUES(a), b = VALUES(b)")


def test_upsert_sql_extra_update():
    assert upsert_sql("t", ["id", "a"], ["id"], "fetched_at = NOW()").endswith(
        "a = VALUES(a), fetched_at = NOW()")


def test_approach_upsert_never_updates_the_unique_key():
    sql = upsert_sql("close_approaches", APPROACH_COLUMNS, ["neo_id", "epoch_ms"])
    update_part = sql.split("ON DUPLICATE KEY UPDATE")[1]
    assert "neo_id =" not in update_part
    assert "epoch_ms =" not in update_part


def test_split_counts():
    # 10 new rows, 3 changed rows (2 each), others unchanged (0)
    assert split_counts(rows_before=100, rows_after=110, affected=16) == LoadCounts(inserted=10, updated=3)
    # re-run with identical data: nothing inserted, nothing changed
    assert split_counts(rows_before=110, rows_after=110, affected=0) == LoadCounts(inserted=0, updated=0)


class FakeCursor:
    """Simulates MySQL's upsert affected-row counts on an in-memory table keyed by 'id'."""

    def __init__(self, existing):
        self.table = dict(existing)
        self.batches = []

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return {"n": len(self.table)}

    def executemany(self, sql, rows):
        self.batches.append(len(rows))
        affected = 0
        for row_id, value in rows:
            if row_id not in self.table:
                affected += 1
            elif self.table[row_id] != value:
                affected += 2
            self.table[row_id] = value
        return affected


def test_upsert_rows_counts_inserts_and_updates():
    cur = FakeCursor({1: "a", 2: "b", 3: "c"})
    rows = [{"id": 1, "v": "a"}, {"id": 2, "v": "CHANGED"}, {"id": 4, "v": "new"}]

    assert upsert_rows(cur, "t", ["id", "v"], ["id"], rows) == LoadCounts(inserted=1, updated=1)


def test_upsert_rows_rerun_is_all_zero():
    cur = FakeCursor({})
    rows = [{"id": i, "v": str(i)} for i in range(5)]
    assert upsert_rows(cur, "t", ["id", "v"], ["id"], rows) == LoadCounts(inserted=5, updated=0)
    assert upsert_rows(cur, "t", ["id", "v"], ["id"], rows) == LoadCounts(inserted=0, updated=0)


def test_upsert_rows_batches_large_inputs():
    cur = FakeCursor({})
    rows = [{"id": i, "v": "x"} for i in range(1200)]
    upsert_rows(cur, "t", ["id", "v"], ["id"], rows)
    assert cur.batches == [500, 500, 200]


def test_upsert_rows_with_no_rows_does_nothing():
    cur = FakeCursor({})
    assert upsert_rows(cur, "t", ["id", "v"], ["id"], []) == LoadCounts()
    assert cur.batches == []


def test_save_aliases_inserts_ignore():
    from pipeline.load import save_aliases

    class Cur:
        def executemany(self, sql, rows):
            self.sql, self.rows = sql, rows

    cur = Cur()
    save_aliases(cur, [{"old_neo_id": "3430309", "numbered_neo_id": "2614134", "designation": "2008 TC4"}])
    assert cur.sql.startswith("INSERT IGNORE INTO neo_id_aliases")
    assert cur.rows == [("3430309", "2614134", "2008 TC4")]
