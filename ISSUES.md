# Issues Analysis

## Summary
| Type | Critical | High | Medium | Low | Total |
|------|----------|------|--------|-----|-------|
| Product Issues | 2 | 1 | 0 | 0 | 3 |
| Code Issues | 0 | 3 | 0 | 0 | 3 |

---

## Product Issues
> Product issues are user-facing problems: broken functionality, missing validation, poor UX, data integrity risks visible to users.

### [P1] The tool says "success" even when the migration is empty or incomplete
**Severity**: Critical

**Location**: `problems/views.py:320`, `:518-545`; `problems/polygon_api.py:399-402`, `:679-686`; `problems/templates/problems/index.html:236-314`

**Problem**: The tool never checks if the result makes sense, and it does not show which steps are done. What happened to me: my tests were first in custom test groups (`first_example`, `remaining`), not in the `tests` group. The tool only reads `tests`, and the page doesn't say so. It got zero tests, but every step went green: the problem was saved with 0 samples, 0 tests were saved, and the upload said "0 test case(s) uploaded to S3 storage under test_cases/1/ successfully." I only found out when I opened the S3 bucket and it was empty.

There are more gaps like this:
- A failed test download is saved as empty text (`polygon_api.py:399-402`) and later skipped (`views.py:518`). Only the server log mentions it.
- "Migrate Test Cases to DB" keeps only the first 260 characters of each test (`views.py:520-521`), but says everything was migrated.
- If test 2 is skipped, storage gets `01` and `03`, while the database numbers its rows 1, 2, 3. So "test 2" means different tests in the two places.
- The four steps have no status, and the test-case button is called "Migrate Test Description to Database" and sits below the long test table (`index.html:314`), so I missed it on my first run.

**Impact**: The judge can end up with no tests or missing tests, so wrong solutions can be accepted. Staff trust the green message, so problems are found late, usually by students.

**Recommended improvement**:
1. Stop, or ask "continue anyway?", when there are 0 tests, 0 samples, or any test is empty or failed to download.
2. Show exact numbers, for example "12 of 14 uploaded, skipped: #3 (empty answer), #7 (download failed)".
3. Show a checklist (Fetched, Problem saved, Tests saved, Uploaded), rename the button, and show which Polygon test group is read.
4. Store the full test (or mark the 260-character copy as a preview), and use the same numbering everywhere.

**Priority rationale**: Number 1 because it happens in normal first-time use, and it happened to me. It puts wrong or missing tests on the judge, and nobody notices until students complain. It also hides P2 and P3: with exact numbers, many of those problems would be seen right away.

### [P2] Re-migrating or undoing a migration is not safe
**Severity**: Critical

**Location**: `problems/views.py:338-339`, `:285-323`, `:435-457`, `:510-543`; `problems/polygon_api.py:677`

**Problem**: On re-migration the tool overwrites database rows by position and never deletes extra ones. If a problem goes from 20 tests to 12, rows 13-20 stay. Samples work the same way. The upload does the opposite: it deletes the whole folder first (when I re-uploaded, the log showed all 28 old files deleted). So the database has 20 tests and storage has 12. The slug is also rebuilt from the title every time, so fixing a typo breaks old links. There is no preview and no confirmation, and no delete or undo. The page shows the public Algopath link straight after migration. If you migrate the wrong or a broken problem, the tool can't remove it. Deleting it in Django admin leaves its test files in storage.

A failed step could delete all the live test files (tested). In the version I first submitted, Upload deleted the old files (`polygon_api.py:677`) and uploaded new ones. Then the same click still downloaded the package from Polygon. If that failed, the error handler deleted the files it had just uploaded. I tested this by adding a forced error right after the upload. The log showed "Uploaded 14 test cases", then "Deleted 28 object(s) under s3://polygon-testcases/test_cases/2/". The page said "all changes have been rolled back", but the problem had no test files left in S3, while the database still said 14 tests. I then removed the forced error and uploaded again to restore the files. To be honest: in the original code this clean-up called `api.delete_azure_blob(...)`, which doesn't exist, so it crashed instead. When I added S3, I connected it to a real delete, which made this risk real. After the review I fixed this part: the upload now runs after all Polygon calls (`views.py:285-323`), the error handler no longer deletes files, and the page shows only one message. Still open: the upload deletes the old files before writing the new ones (`polygon_api.py:677`), so if the upload itself fails halfway (for example, the network drops at file 7), the folder still ends up empty. Point 3 below covers this.

**Impact**: The website and judge disagree ("my output matches the test shown, but I got Wrong Answer"). A live problem can lose all its tests after one failed re-upload, and mistakes can't be reversed.

**Recommended improvement**:
1. Make re-migration a full replace: in one transaction, delete old test and sample rows and create them again.
2. Show "12 tests (was 20): 8 will be removed" and ask for confirmation. Keep the slug fixed after the first import.
3. Fetch everything from Polygon before uploading. Upload to a temporary folder and switch only when all worked.
4. Add a "Delete / Unpublish" action that removes database rows and storage files together.

**Priority rationale**: Number 2 because the damage hits problems already live for students, and deleted files can't come back. It is below P1 because it needs a re-migration or a failure, while P1 can happen every time. It is above P3 because it directly causes wrong data, while P3 only fails to catch it.

### [P3] The review screen does not let you really review the problem
**Severity**: High

**Location**: `problems/templates/problems/index.html:207`; `problems/views.py:148-183`, `:201-213`; `problems/polygon_api.py:129-231`, `:351`, `:742`

**Problem**: The page should let staff check a problem before migrating, but it doesn't show it properly or say which version it is.
- **Statement shows as raw HTML (tested).** I see `<p>`, `<ul>`, `<span class="tex-font-style-bf">` instead of formatted text (`index.html:207`). My own statement says "an over of exactly balls". The 6 is missing because of a maths format mistake I made on Polygon, and I didn't notice it because the text was full of tags.
- **Solution hidden on first fetch.** It is only fetched when the problem is already in the database (`views.py:148-183`).
- **Mixed versions.** The statement comes from the built package, the tests from the live working copy. My only package has an empty `tests` group, but the tool migrated 14 tests from the working copy without telling me.
- **Steps can use different data.** Tests are cached in Redis for 30 minutes. After that, later buttons quietly download again from Polygon.
- **Nothing recorded.** The `Problem` table doesn't store which Polygon revision was migrated.

**Impact**: Mistakes like my missing number can go live, and the solution can't be checked first. The statement may not match the saved tests, and the website and judge can have different versions.

**Recommended improvement**:
1. Show the statement as formatted HTML (cleaned to safe tags) with MathJax, like Polygon.
2. Fetch the main solution on every fetch.
3. Take everything from one built package revision, show it on the page, and save it on the `Problem` record.
4. Make every step use the data captured at fetch time.

**Priority rationale**: The review screen is the safety check before a problem goes live, and it would catch many mistakes from P1 and P2. It is number 3 because it doesn't damage data by itself, it only fails to stop bad data.

**Why not other product issues**: The fetch is slow (the page warns "3-4 minutes" and every click repeats it), and duplicate titles fail with a raw database error (see Q3). These cost time or are rare, but don't put wrong tests in front of students.

---

## Code Issues
> Code issues are technical problems: bugs, security vulnerabilities, performance problems, code quality concerns, architectural issues.

### [C1] One very large view does everything, and every button repeats the whole fetch
**Severity**: High

**Location**: `problems/views.py:88-562` (`index()`)

**Problem**: The whole tool is one function, `index()`, about 480 lines. All four buttons post to the same URL, and it decides what to do from hidden form fields:
```python
migrate_to_storage = request.POST.get('migrate_to_storage')
migrate_to_db = request.POST.get('migrate_to_db')
```
It calls Polygon, parses HTML, writes to the database and uploads to storage. The fetch part always runs, so every click downloads the problem again (about 36 Polygon calls for my problem). The "fetch main solution" code is written twice (`:155-183` and `:465-490`), and validation raises a plain `Exception` (`:329-331`).

**Impact**: Changing one button risks breaking another, and nothing can be tested on its own. Every click is slow, and a new developer must read all of it to understand one action. I had to, for the documentation.

**Recommended improvement**:
1. Give each action its own URL and view: fetch, save problem, save tests, upload.
2. Move the work into small functions (`fetch_problem`, `save_problem`, `save_test_cases`, `upload_tests`) that can be tested alone.
3. Fetch once and reuse the result (see C2). Use Django forms for validation.

**Priority rationale**: Number 1 because every fix, including the fixes for P1-P3, has to go through this one function. It slows the team down the most.

### [C2] There is no reliable place where the imported test data lives
**Severity**: High

**Location**: `problems/polygon_api.py:714-740`, `:742`, `:789`; `problems/views.py:201-213`, `:419-428`, `:498-505`

**Problem**: The full tests only live in a Redis cache that expires after 30 minutes, and that is how data passes between buttons. The database copy is cut to 260 characters, so it can't replace it. The upload reads the cache, or downloads from Polygon again. The "read cache or download" block is copy-pasted four times.

The cache-clearing function never works. It looks for `oj_dev_with_redis_storage_test_cases_{db_problem_id}*`, but the cache is saved as `polygon_migration_test_cases_{polygon_id}`. They never match, so it deletes nothing.

**Impact**: It is the code-side cause of P2 and P3: steps see different data depending on timing. A function that looks like it works but doesn't will mislead the next developer.

**Recommended improvement**:
1. On fetch, save one snapshot (statement, full tests, revision) somewhere permanent.
2. Make the database step and the upload both read from it.
3. Keep Redis only as an optional speed-up, with keys and connection in one place.

**Priority rationale**: Number 2 because it causes the data mix-ups in P2 and P3. It is below C1 because it can only be fixed cleanly once the view is split.

### [C3] Errors are hidden, the "rollback" can't undo storage, and the migration flow has no tests
**Severity**: High

**Location**: `problems/polygon_api.py:310-311`, `:399-402`; `problems/views.py:186`, `:547-553`; `problems/tests.py` (empty)

**Problem**: Many helpers catch every error and return an empty value. `get_test_cases` returns `[]` on any error, so the test count becomes 0 just because Polygon timed out. The caller can't tell "nothing" from "broken". This is the code reason for P1. The flow is wrapped in `transaction.atomic()` (`views.py:186`), which only rolls back the database, not S3. So the error handler used to "fix" things by deleting storage files, which is how P2's wipe happened. I removed that, but a half-finished upload still can't be undone (`views.py:312-317`).

The only tests are my 8 storage tests (`problems/test_storage.py`). The migration flow in `views.py` has none, and `problems/tests.py` is empty. During setup the first fetch crashed with "column problems_problem.notes does not exist" because two model fields had no migration, and I had to add one. While adding S3, I found the handler called `delete_azure_blob`, which doesn't exist. Simple tests would have caught both.

**Impact**: Failures turn into "success with less data", and a late failure can delete good data. Without tests, refactoring C1 and C2 is risky.

**Recommended improvement**:
1. Let errors rise to one place that shows a clear message. Where skipping is fine, count it and show it.
2. Change storage only after the database work succeeds, using a temporary folder, so nothing needs deleting on failure.
3. Add tests with Polygon and storage faked (like my `problems/test_storage.py`), and run them plus `makemigrations --check` in CI.

**Priority rationale**: Number 3 because it doesn't block changes like C1 or cause mix-ups like C2. But it is why problems stay invisible, and tests are what make fixing C1 and C2 safe.

**Why not other code issues**: The checker list is written twice (`views.py:254`, `models.py:43`), the Algopath URL is hard-coded, full form data is written to the logs, the app won't start without Polygon keys even for `migrate` (`settings.py:127`), and the `User` model has many unused fields. Worth cleaning, but less important.

---

## Edge Case Analysis
### Q1
> A Polygon problem has 0 sample test cases but 15 regular test cases. What happens when you migrate this problem?

**Tested.** Actions: all three buttons. I made a new Polygon problem "Two Sum" (ID 636419) with 20 tests and did not tick "Use in statements" on any of them (I used 20 instead of 15 so I could reuse it for Q2; the number doesn't change anything). Fetch showed every test as "Sample: No" with no warning. "Create/Update problem in Database" said "Problem 'two sum' created in database successfully" and saved 0 sample rows, because only tests marked "use in statements" become samples (`views.py:433`). "Migrate Test Cases to DB" saved 20 rows, and Upload put 40 files in `test_cases/3/`. So everything "works", but students get no examples and nobody is told. With my first problem I saw a worse version: my tests were in the wrong group, so it saved 0 samples and 0 tests, and every step still said success (P1).

### Q2
> A problem is migrated with 20 test cases. Later, the problem setter removes 8 test cases on Polygon (now 12 remain). The problem is re-migrated. What happens?

**Tested** on the same problem (636419). After the first migration the database had 20 rows and S3 had 40 files. I deleted tests 13-20 on Polygon, fetched again (it showed 12) and clicked all three buttons again.

| | Before | After re-migration |
|---|---|---|
| `test_case_count` on the problem | 20 | 12 |
| Test case rows in the database | 20 | **20** |
| Files in S3 `test_cases/3/` | 40 | 24 |

"Create/Update problem in Database" set the count to 12. Upload deleted the whole folder and uploaded 12 tests. "Migrate Test Cases to DB" overwrote rows 1-12 and left rows 13-20 in place (`views.py:524-543` never deletes rows), and still said it was successful. So the database has 20 tests, storage has 12 and the problem says 12, with no warning. In admin, the old long test 15 is still there although it no longer exists on Polygon or in S3. Samples are saved the same way (`views.py:435-457`), so removed samples would also stay.

### Q3
> Two different Polygon problems have the exact same title: "Two Sum". You migrate the first one successfully. Then you try to migrate the second one. What happens?

**Tested.** The first "Two Sum" (636419) was already in the database with slug `two-sum`. I made a second problem (636427) with the same name, fetched it (slug shown: `two-sum`) and clicked "Create/Update problem in Database". It failed with: *"Migration failed and all changes have been rolled back. Reason: duplicate key value violates unique constraint "problems_problem_slug_key" DETAIL: Key (slug)=(two-sum) already exists."* (log: `IntegrityError` at `views.py:362`). The slug is made from the title (`views.py:338-339`) and must be unique (`models.py:58`), and the tool never checks or adds a suffix. The other buttons stay blocked because the problem isn't in the database.

So the second problem can't be migrated at all until someone changes a title, and the error is raw database text instead of "a problem with this title already exists".

### Q4
> When test cases are saved to the database via "Migrate Test Cases to DB", some data is intentionally discarded. What data is lost? Why might this cause problems?

**Tested.** Action: "Migrate Test Cases to DB" (`views.py:512-543`). In problem 636419, test 15 has an input of 100 numbers. S3 got the full file (log: "Uploaded s3://polygon-testcases/test_cases/3/15 (1006 bytes)"), but in the database the same input is exactly 260 characters and ends in the middle of a number (`...468804211 88323`). The page still said the migration was successful.

What is lost:
1. Everything after the first 260 characters of each input and output (`views.py:520-521`). This is the one I tested.
2. In the same code, spaces and newlines at the end are removed (`.rstrip()`), and tests with an empty input or output are not saved at all (`views.py:518`).
3. The original Polygon test number. Rows get a new `order`, so after a skipped test the numbers don't match Polygon or storage.
4. `manual`, test groups and points are never stored.

Why it matters: the rows look complete and nothing marks them as cut. Anything that later reads tests from the database (showing, re-judging, exporting) gets broken data, and the database can't rebuild storage (C2). Samples are saved without the cut, so the same test looks different in two tables, and "test 5" in admin may not be test 5 in storage.

---

## Severity Guidelines
| Severity | Definition | Examples |
|----------|------------|----------|
| **Critical** | System broken, security vulnerability, data loss | SQL injection, authentication bypass, data corruption |
| **High** | Major functionality broken, significant data integrity risk | Feature doesn't work, orphaned records, race conditions |
| **Medium** | Feature partially broken, poor UX, code maintainability | Missing validation, confusing errors, code duplication |
| **Low** | Minor issues, cosmetic, best practice violations | Unused imports, inconsistent formatting, missing logs |

---

## Notes
- **Security (outside the top three):** tag names go into the page's JavaScript without escaping (`index.html:365-366` uses `|safe`, `:575` uses `innerHTML`), so a staff member could create a tag that runs code in other staff members' browsers. Fix: use `json_script` and `textContent`.
- **Setup:** the missing migration (C3) and needing Polygon keys even to run `migrate` slowed the first setup.
- **Polygon tip:** the tool only reads the `tests` group. The statement comes from the latest built package, but tests come from the live working copy. In my Q2 test, the deleted tests disappeared from the tool without a commit or a new package.
