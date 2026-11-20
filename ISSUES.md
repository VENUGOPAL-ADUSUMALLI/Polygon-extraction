

## Product Issues

### [P1] The tool says "success" even when the migration is empty or incomplete

**Severity**: Critical

**Location**: `problems/views.py:519–546` (test cases to DB), `problems/views.py:224` (upload message), `problems/polygon_api.py:399–402` and `:680–686` (failed or empty tests are skipped)

**Description**:
The tool never checks whether the result makes sense. It shows a green success message even when tests are missing.

What happened to me: when I first created my problem on Polygon, my tests ended up in custom test groups instead of the default `tests` group. The tool only reads `tests`, so it got **zero tests**. But every step still went green:
- Fetch simply showed no tests, with no warning.
- "Create/Update problem in Database" saved the problem with **0 samples**.
- "Migrate Test Cases to DB" saved **0 tests** and said it was successful.
- Upload said **"0 test case(s) uploaded to S3 storage under test_cases/1/ successfully."**

I only found out because I opened the S3 bucket and it was empty.

From reading the code, there are more ways tests disappear quietly:
- If downloading a test from Polygon fails, the code stores it as empty text instead of stopping (`polygon_api.py:399–402`). Later, empty tests are just skipped (`views.py:519`, `polygon_api.py:683`), and only a line in the server log mentions it.
- "Migrate Test Cases to DB" keeps only the **first 260 characters** of every input and output (`views.py:521–522`). The message still says everything was migrated, and nothing in the data shows it was cut.
- Uploaded files are numbered by the test's position. If test 2 is skipped, storage gets `01` and `03` but no `02`, while the database numbers its rows 1, 2, 3… So "test 2" can mean two different tests in the two places.

**Impact**:
- The judge can end up with no tests or missing tests. Wrong solutions could then be accepted, which affects students and contest results.
- Staff trust the green message, so problems are found late, usually by users.
- Finding out what really happened needs access to the server logs.

**Suggested Fix**:
1. Check before migrating. Stop, or ask for an explicit "continue anyway", when there are 0 tests, 0 samples, or any test failed to download or is empty.
2. Show exact numbers in every result, for example "14 of 14 tests uploaded", or "12 of 14 uploaded, skipped: #3 (empty answer), #7 (download failed)".
3. Make it clear that the database copy is a 260-character preview, or store the full test.
4. Use the same numbering in the database and in storage.

---

### [P2] What you review is not always what gets migrated

**Severity**: High

**Location**: `problems/polygon_api.py:129–231` (statement from the built package), `:351` (tests from the live working copy), `:742` (30-minute cache); `problems/views.py:242–254`, `:420–429`, `:499–506` (each step reads the cache or downloads again); `problems/models.py` (no revision stored)

**Description**:
The data for one problem comes from different places at different times, and the page never says which version you're looking at.
- **Statement and tests come from different versions.** The statement is read from the latest *built package*. The tests are read from the *current working copy* on Polygon. I checked this on my own problem: my only package is revision 1, and its `tests` group is empty, but the tool showed and migrated 14 tests, because those come from the working copy. So the page combined the statement from revision 1 with tests that were never built into any package, without telling me.
- **Steps can use different versions.** Fetch keeps the tests in Redis for 30 minutes, and the later buttons read from there. If more than 30 minutes pass between clicks, the tool quietly downloads the tests from Polygon again. If the problem setter changed tests in between, the database step and the upload can get different tests.
- **Nothing is recorded.** The `Problem` table has no field for which Polygon revision was migrated, so later nobody can tell what is live.

**Impact**:
- The statement can show samples or limits that don't match the tests that were saved.
- The website (database) and the judge (storage) can end up with different versions of the tests.
- It confused me. I had to dig into packages vs. working copy to understand why a READY package didn't match what the tool showed. A staff member shouldn't need to know Polygon internals to migrate a problem.

**Suggested Fix**:
1. Take everything for one import (statement and tests) from **one built package revision**, instead of mixing the package with the live working copy.
2. Show the revision on the page ("Revision 1, built 20 Nov 15:02"), and warn if Polygon has changes that aren't in a built package yet.
3. Save the revision number and time on the `Problem` record.
4. Have every step use the same data captured at fetch time, instead of a cache that silently refreshes from Polygon.

---

### [P3] Re-migrating a changed problem leaves old data behind

**Severity**: High

**Location**: `problems/views.py:436–458` (samples), `:511–544` (test cases), `:339–353` (update of an existing problem, slug rewritten). There is no delete of old rows anywhere in `views.py`.

**Description**:
When a problem is migrated again, the tool overwrites rows by position and never deletes the extra ones.
- If a problem had 20 tests and now has 12, rows 1–12 are overwritten, but **rows 13–20 stay**, while the problem's test count says 12.
- Samples work the same way. If the setter goes from 3 samples to 2, the old third sample stays on the problem page.
- The upload works differently: it deletes the whole folder first and uploads again. I saw this when re-uploading: the log showed all 28 old files deleted before the new ones were written. So after a re-migration, **the database has 20 tests and storage has 12.**
- The problem's URL name (slug) is rebuilt from the title on every re-migration. Fixing a typo in the title changes the public link, and old links break.
- There is no preview of what will change and no confirmation step.

**Impact**:
- The website and admin show tests that no longer exist on Polygon.
- The website and the judge disagree, which leads to confusing support cases ("my output matches the test shown, but I got Wrong Answer").
- Fixing tests after a contest is normal, so this will happen. Re-migration looks like a full update but isn't, so nobody knows they have to clean up by hand.

**Suggested Fix**:
1. Make re-migration a full replace: inside the same transaction, delete the problem's old test and sample rows and create them again. Or match tests by their Polygon test number and delete the ones that are gone.
2. Before applying, show a summary like "12 tests (was 20): 8 will be removed", and ask for confirmation.
3. Keep the slug the same after the first import, unless someone changes it on purpose.
4. Use the same "replace everything" approach for the database and storage so they can't drift apart.

**Why not other product issues**: I also noticed that the four steps are separate buttons with no "done / not done" status. I actually missed the test-case button at first, because it sits below the test table and is labelled "Migrate Test Description to Database". The fetch is also slow (the page itself warns it "may take 3–4 minutes"). Both are real, but they cost time rather than producing wrong data, and a confused user will notice and ask. Duplicate titles fail with an error (see Q3) and are rare. So I kept the top three for issues that can put wrong tests in front of the judge.

---

## Code Issues

### [C1] One very large view does everything, and every button repeats the whole fetch

**Severity**: High

**Location**: `problems/views.py:88–564` (`index()`), cache-or-download block repeated at `views.py:242–254`, `:420–429`, `:499–506` and `polygon_api.py:657`

**Description**:
The whole tool is a single function, `index()`, about 480 lines long. All four buttons post to the same URL, and the function works out what to do from hidden form flags. The same function also calls Polygon, parses HTML, writes to the database and uploads to storage.

Because the "fetch" part always runs, **every button click downloads the problem again**: problem info twice, the package ZIP, the checker twice, the test list twice. For my 14-test problem, the first fetch made about 36 Polygon calls. The same "read the cache, or download from Polygon" block is copy-pasted four times. Validation is done by raising a plain `Exception` (for example, a missing difficulty at `views.py:329–331`), so every problem looks the same to the error handler.

**Impact**:
- Any change, like adding a step or changing one button, means editing this one long function, with a high chance of breaking another button.
- It can't be tested piece by piece. You need Polygon, Redis and the database for any test.
- Every click is slow, and it uses Polygon's API much more than needed.
- New developers have to read the whole function to understand any single action. I did, while writing the documentation.

**Suggested Fix**:
1. Give each action its own URL and view: fetch, save problem, save tests, upload.
2. Move the work into small functions or a service class (`fetch_problem`, `save_problem`, `save_test_cases`, `upload_tests`) that can be tested on their own.
3. Fetch once, keep the result (see C2), and let the other actions reuse it instead of downloading again.
4. Use Django forms for validation (difficulty required, at least one tag) instead of raising exceptions.

---

### [C2] There is no reliable place where the imported test data lives

**Severity**: High

**Location**: `problems/polygon_api.py:742` (`store_test_cases_in_redis`, 30-minute expiry), `:789` (`get_test_cases_from_redis`), `:714–740` (`delete_problem_test_case_cache`); `problems/views.py:521–522` (260-character limit); `polygon_api.py:657` (upload reads the cache or Polygon)

**Description**:
The full test data is only ever kept in a **Redis cache that expires after 30 minutes**. That cache is how the data is passed from one button to the next. The database copy is cut to 260 characters, so it can't be used to rebuild the tests. The upload doesn't read the database at all: it reads the cache again, or downloads from Polygon if the cache has expired.

I first noticed this as "after 30 minutes the tool goes back to Polygon instead of using what we already saved". While looking into it I found that it can't simply read from the database, because the database doesn't hold the full tests.

There is also a cache-clearing function, `delete_problem_test_case_cache`, which the upload calls before running. It looks for keys starting with `oj_dev_with_redis_storage_test_cases_` + the database ID, but the cache is written with keys starting with `polygon_migration_test_cases_` + the Polygon ID. So it never finds anything. It looks like it works, but it does nothing.

**Impact**:
- This is the code-side cause of P2: different steps can see different data, depending on timing.
- It's the reason the database can't be used for anything that needs the real tests.
- Redis is being used to hold data that matters. If Redis is restarted or the cache expires, the next step quietly goes back to Polygon.
- Code that looks like it clears the cache but doesn't misleads whoever reads it next.

**Suggested Fix**:
1. When a problem is fetched, save one snapshot of it (statement and full tests, tagged with the Polygon revision) somewhere permanent: a database table, or the storage bucket itself.
2. Make the database step and the upload both read from that snapshot.
3. Keep Redis only as an optional speed-up, never as the only copy.
4. Remove or fix `delete_problem_test_case_cache` so the cache keys are defined in one place.

---

### [C3] Errors are hidden instead of reported, and nothing catches mistakes before they ship

**Severity**: High

**Location**: `problems/polygon_api.py:310–311` (`get_test_cases` returns `[]` on any error), `:399–402` (failed download becomes empty text), `:742–787` and `:789–842` (Redis helpers only log errors), `:409–435` (`get_custom_checker_info` returns `None` on error); `problems/tests.py`, `users/tests.py` (empty)

**Description**:
Many helper functions catch every error, write a log line, and return an empty value as if nothing went wrong:
- `get_test_cases` returns an empty list on any error, so the test count shown can become 0 just because Polygon timed out.
- `get_all_test_cases` turns a failed download into empty text, and that test is later skipped.
- If saving to Redis fails, the error is only logged, and the next step quietly downloads from Polygon again.

The calling code can't tell "there's nothing" apart from "something broke". This is the code-side reason behind P1.

There are also no automated tests at all. The test files are empty. I ran into the result of this during setup: the code had two model fields (`notes`, `genie_chat`) without a matching migration, so the very first fetch crashed with "column problems_problem.notes does not exist" until I generated the missing migration. While swapping the storage to S3, I also found that the error handler called `api.delete_azure_blob(...)`, a method that doesn't exist, so that clean-up could never have worked. Simple automated checks would have caught both.

**Impact**:
- Failures turn into "success with less data" instead of a clear error. That is exactly how P1 happens.
- Bugs reach users and are only found by hand, like the missing migration I had to fix before anything worked.
- Without tests, refactoring C1 and C2 is risky, because there's nothing to show you didn't break something.

**Suggested Fix**:
1. Let errors rise up to one place that shows a clear message, instead of returning empty values. Where skipping is acceptable, count what was skipped and show it (as in P1).
2. Add basic automated tests for each step: parsing the statement, saving the problem, saving tests, uploading. Fake the Polygon and storage calls. (I added this kind of test for the new S3 storage code: `problems/test_storage.py`.)
3. Add a simple CI check that runs the tests and `python manage.py makemigrations --check`, so a missing migration fails the build instead of crashing the app.

**Priority rationale**:
It ranks below C1 and C2 because it doesn't block changes the way C1 does, or cause the data mix-ups that C2 does. But it's the reason problems stay invisible, and it's what makes fixing C1 and C2 safe, so it belongs in the top three.

**Why not other code issues**: I also noticed the Redis connection code is copy-pasted in four functions, the Algopath URL is hard-coded in the template, the full form data and the parsed statement are written to the logs, and the models carry many fields from the wider platform that this tool never uses (the `User` model has college, Discord ID and so on, and the `contents` app exists only because `User` points to it). These are worth cleaning up, but they don't block the team or affect the data as much as the three above.

---

## Edge Case Analysis

### Q1

> A Polygon problem has 0 sample test cases but 15 regular test cases. What happens when you migrate this problem?

**Based on reading the code, plus a related case I saw myself.**

- **Fetch:** shows 15 tests. None has the "Sample" badge, and there is no warning.
- **Create/Update problem in Database:** the problem is saved, but **0 sample rows** are created, because only tests marked "use in statements" become samples (`views.py:434`). The statement on the page has no examples. Nothing warns that a problem without examples is unusual.
- **Migrate Test Cases to DB:** saves 15 rows, all marked as not a sample.
- **Upload:** writes 30 files (`01`…`15` plus `.a` files). This step doesn't care about samples.

So the migration "works", but users get a problem with no examples, and nobody is told. I saw a stronger version of this myself: with my tests in the wrong test group, the problem was saved with 0 samples **and** 0 tests, and every step still showed success.

---

### Q2

> A problem is migrated with 20 test cases. Later, the problem setter removes 8 test cases on Polygon (now 12 remain). The problem is re-migrated. What happens?

- **Create/Update problem in Database:** finds the existing problem by Polygon ID and updates it. The test count becomes 12. Samples are overwritten by position, and extra old samples are not deleted.
- **Migrate Test Cases to DB:** loads the 20 existing rows and overwrites rows 1–12 with the new tests. **Rows 13–20 are left as they were** (`views.py:525–544`, no delete). The database now has 20 test rows, while the problem says it has 12.
- **Upload to storage:** deletes everything in `test_cases/<id>/` first, then uploads the 12 tests. When I re-uploaded my problem, the log showed all 28 old files deleted before the new ones were written. Storage ends up correct, with 12 tests.

Result: **the database has 20 tests and storage has 12.** The website and admin show 8 tests that no longer exist, and no message mentions it. Also, if the test data changed within 30 minutes of an earlier fetch, the old cached version may be used unless the cache has expired (see P2).

---

### Q3

> Two different Polygon problems have the exact same title: "Two Sum". You migrate the first one successfully. Then you try to migrate the second one. What happens?

- **Fetch** works normally for the second problem.
- **Create/Update problem in Database:** the tool looks the problem up by **Polygon ID**. The second problem has a different ID, so it tries to **create** a new row. The slug is made from the title, so both become `two-sum`, and the `slug` column must be unique (`models.py:58`). The database rejects the insert with a duplicate-key error.
- The whole request is rolled back, and the page shows "Migration failed and all changes have been rolled back. Reason:" followed by the raw database error about the duplicate `slug`.
- "Migrate Test Cases to DB" and "Upload" for the second problem are blocked, because they need the problem to exist in the database first.

So the second problem **cannot be migrated at all** until one of the titles is changed on Polygon, and the error message talks about a database constraint instead of telling the user "a problem with this title already exists".

---

### Q4

> When test cases are saved to the database via "Migrate Test Cases to DB", some data is intentionally discarded. What data is lost? Why might this cause problems?

**Based on reading the code** (`views.py:513–544`, `polygon_api.py:351–407`). My own tests are very short (for example `1 0 0 0 0 0` → `Venu`), so cutting didn't show up for my problem.

What is lost:
1. **Everything after the first 260 characters** of each input and output (`views.py:521–522`). A test with 100,000 numbers keeps only its beginning, and it can be cut in the middle of a number.
2. **Spaces and newlines at the end** of input and output (`.rstrip()`, `views.py:514–515`).
3. **Tests with an empty input or empty answer** are not saved at all (`views.py:519`).
4. **The test's original number on Polygon** is not kept. Rows only get a new running number (`order`), so after a skipped test the numbers no longer match Polygon or storage.
5. Some Polygon details are never fetched or stored at all, for example whether a test was typed by hand or generated (`manual`, fetched but not saved), and test groups and points.

Why this can cause problems:
- The rows look like complete tests, and nothing marks them as cut. Anyone, or any future feature, that reads tests from the database (showing full tests, re-uploading, re-judging, exporting) gets broken data without knowing.
- It's why the database can't be used to rebuild the storage files (C2).
- Samples are saved without this 260-character cut (`views.py:439–457`), so the same test can look different in the samples table and in the test-case table.
- Because numbering is different, "test 5" in the admin may not be test 5 in storage or on Polygon, which makes debugging a wrong answer harder.

---

## Severity Guidelines

| Severity | Definition |
|----------|------------|
| **Critical** | System broken, security vulnerability, data loss |
| **High** | Major functionality broken, significant data integrity risk |
| **Medium** | Feature partially broken, poor UX, code maintainability | 
| **Low** | Minor issues, cosmetic, best practice violations |

---

## Notes

Other things I ran into while using the tool, which didn't make the top three:

- **Steps are hard to follow.** There are four separate buttons with no status showing what's done. The test-case button is below the long test table and is labelled "Migrate Test Description to Database", so I missed it on my first run. You can also upload to storage without ever saving the tests to the database.
- **Only the `tests` group is read.** This isn't mentioned anywhere in the tool. I lost time because my tests were in other groups.
- **Slow.** Every click re-downloads the problem from Polygon. For my 14-test problem that's about 36 API calls per fetch.
- **Main solution only shows after the problem is in the database.** The tool only asks Polygon for the solution once a DB record exists, so on a first fetch you can't review it before migrating.
- **Setup:** the missing migration (see C3) and the hard requirement for Polygon keys even to run `migrate` slowed the first setup down.
