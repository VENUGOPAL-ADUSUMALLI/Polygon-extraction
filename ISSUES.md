# Issues Analysis

## Summary

| Type | Critical | High | Medium | Low | Total |
|------|----------|------|--------|-----|-------|
| Product Issues | 2 | 1 | 0 | 0 | 3 |
| Code Issues | 0 | 3 | 0 | 0 | 3 |

---

## Product Issues
### [P1] No check on the migration result

**Severity**: Critical
**Location**: `problems/views.py:320`, `:518-545`; `problems/polygon_api.py:399-402`; `problems/templates/problems/index.html:236-314`

**Description**:
My tests were in custom groups, not in `tests`, so the tool picked up 0 tests. Every step still went green, including "0 test case(s) uploaded successfully". I found out only when I opened the bucket.

**Impact**:
- Judge can go live with no tests, so wrong solutions pass
- Failed downloads are saved as empty and skipped, only the server log says so
- DB keeps 260 chars per test but still reports "migrated"
- Nobody notices until a student complains

**Suggested Fix**:
Stop (or ask to continue) on 0 tests / 0 samples / empty tests, and show real counts like "12 of 14 uploaded, skipped #3, #7". A small step checklist on the page would also help, I missed the test-case button on my first run because it sits under the long table.

### [P2] Re-migration leaves old rows and can wipe storage

**Severity**: Critical
**Location**: `problems/views.py:338-339`, `:435-457`, `:510-543`; `problems/polygon_api.py:677`

**Description**:
Re-migration overwrites DB rows by position and never deletes the extra ones, while the upload deletes the whole storage folder first. No preview, no confirm, no undo.

**Impact**:
- 20 → 12 tests leaves 20 rows in DB and 12 files in S3, so site and judge disagree
- Upload failing halfway leaves the folder empty
- Slug is rebuilt from the title every time, fixing a typo breaks old links

I also tested a forced error after upload. The old error handler deleted all 28 live files and the page said "rolled back". I fixed that part already (upload runs last, handler no longer deletes), but delete-before-upload is still there.

**Suggested Fix**:
Do a full replace in one transaction (delete old test and sample rows, insert new). Upload to a temp folder and swap only when done. Keep the slug fixed after first import, and add a Delete/Unpublish action.

### [P3] Review screen doesn't let you review

**Severity**: High
**Location**: `problems/templates/problems/index.html:207`; `problems/views.py:148-183`; `problems/polygon_api.py:351`, `:742`

**Description**:
The statement shows as raw HTML tags, and the solution is only fetched if the problem is already in the DB. Statement comes from the built package, tests from the working copy, and nothing records which revision was used.

**Impact**:
- I lost a "6" in my statement from a maths typo and didn't see it in all the tags
- Statement and tests can be from different versions
- Cache expires after 30 min, then later buttons just download again

**Suggested Fix**:
Render the statement as safe HTML with MathJax, fetch the solution every time, and take everything from one package revision and save it on `Problem`.

---

## Code Issues

### [C1] One 480-line view does everything

**Severity**: High
**Location**: `problems/views.py:88-562` (`index()`)

**Description**:
All four buttons post to `index()` and it branches on hidden form fields. The fetch runs every time, so each click re-downloads the problem (about 36 Polygon calls for mine).

**Impact**:
- Changing one button can break another
- Nothing can be unit tested
- Fetch-solution code is written twice, validation raises plain `Exception`

**Suggested Fix**:
One URL and view per action, with the actual work in small functions (fetch, save problem, save tests, upload). Use Django forms for validation.

### [C2] Test data only lives in a 30-min cache

**Severity**: High
**Location**: `problems/polygon_api.py:714-740`, `:789`; `problems/views.py:201-213`, `:419-428`, `:498-505`

**Description**:
Full tests are only in Redis, and that's how data moves between buttons. The DB copy is cut to 260 chars so it can't replace it. The cache-clear function looks for `oj_dev_with_redis_storage_test_cases_*` but keys are `polygon_migration_test_cases_*`, so it never deletes anything.

**Impact**:
- Steps can see different data depending on timing (this is behind P2 and P3)
- "Read cache or download" block is copy-pasted 4 times
- Dead function that looks like it works

**Suggested Fix**:
Save one snapshot at fetch time (statement, full tests, revision) and make every step read from it. Keep Redis only as a speed-up.

### [C3] Errors swallowed, rollback can't undo S3, no tests

**Severity**: High
**Location**: `problems/polygon_api.py:310-311`, `:399-402`; `problems/views.py:186`, `:547-553`; `problems/tests.py` (empty)

**Description**:
Helpers catch every exception and return empty, so a Polygon timeout looks like "0 tests". `transaction.atomic()` rolls back the DB but not S3.

**Impact**:
- Failures turn into "success with less data" (the code side of P1)
- A late failure could delete good files (how the P2 wipe happened)
- No tests on the flow. A missing DB migration and a call to `delete_azure_blob` (doesn't exist) both shipped

**Suggested Fix**:
Let errors go up to one handler and count anything skipped. Write to storage only after the DB step succeeds. Add tests with Polygon and storage mocked, plus `makemigrations --check` in CI.

---

## Edge Case Analysis

### Q1

> A Polygon problem has 0 sample test cases but 15 regular test cases. What happens when you migrate this problem?

Tested with a new problem "Two Sum" (636419), 20 tests, none marked "use in statements". Fetch showed all as "Sample: No" with no warning. DB step said "created successfully" and saved 0 samples (`views.py:433`), test step saved 20 rows, upload put 40 files in S3. Everything "works", students just get no examples and nobody is told.

### Q2

> A problem is migrated with 20 test cases. Later, the problem setter removes 8 test cases on Polygon (now 12 remain). The problem is re-migrated. What happens?

Same problem. Deleted tests 13-20 on Polygon, fetched again (showed 12), ran all three buttons. `test_case_count` went 20 → 12 and S3 went 40 → 24 files, but the DB still had all 20 rows. The test step overwrites rows 1-12 and never deletes (`views.py:524-543`), and still says success. Old test 15 is still in admin even though it's gone from Polygon and S3. Samples behave the same way.

### Q3

> Two different Polygon problems have the exact same title: "Two Sum". You migrate the first one successfully. Then you try to migrate the second one. What happens?

Made a second "Two Sum" (636427). The DB step failed with a raw error: `duplicate key value violates unique constraint "problems_problem_slug_key"` (`IntegrityError`, `views.py:362`). Slug comes from the title and must be unique, and the tool never adds a suffix. So the second problem can't be migrated at all until someone renames one.

### Q4

> When test cases are saved to the database via "Migrate Test Cases to DB", some data is intentionally discarded. What data is lost? Why might this cause problems?

Checked test 15 of 636419 (100 numbers). S3 got the full 1006 bytes, DB has exactly 260 chars and cuts off mid-number (`...468804211 88323`). Page said success.

Lost: everything after 260 chars of input and output (`views.py:520-521`), trailing whitespace (`.rstrip()`), tests with empty input/output are skipped entirely, the original Polygon test number (so "test 5" in admin may not be test 5 in storage), and groups/points/`manual`.

Rows look complete and nothing marks them as cut, so anything reading tests from the DB (display, re-judge, export) gets broken data, and the DB can't be used to rebuild storage.

---

## Notes
- **Security (outside the top three):** tag names go into the page's JavaScript without escaping (`index.html:365-366` uses `|safe`, `:575` uses `innerHTML`), so a staff member could create a tag that runs code in other staff members' browsers. Fix: use `json_script` and `textContent`.
- **Setup:** the missing migration (C3) and needing Polygon keys even to run `migrate` slowed the first setup.
- **Polygon tip:** the tool only reads the `tests` group. The statement comes from the latest built package, but tests come from the live working copy. In my Q2 test, the deleted tests disappeared from the tool without a commit or a new package.
