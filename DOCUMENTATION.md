# Polygon Migration Tool Walkthrough

This tool takes a problem that we write on Codeforces Polygon and brings it into our platform:

- the problem (statement, limits, tags, samples, test cases) goes into PostgreSQL
- the test files go into cloud storage (AWS S3), which is what the judge reads

The whole app is one page. You enter a Polygon problem ID and click four buttons, one after the other. Below I go through each step in the same order I did it.

---

## Step 0: Set up the project

You need Python 3.11, Docker, a Polygon account and an S3 bucket.

```bash
git clone <repo-url> && cd Polygon-migration-assignment
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirement.txt

docker compose up -d                 # starts PostgreSQL 15 + Redis 7

cd PolygonMigration
cp .env.example .env                 # then fill in the values (see below)
python manage.py migrate
python manage.py createsuperuser     # this is your login for the tool
python manage.py runserver           # http://127.0.0.1:8000
```

What goes in `PolygonMigration/.env` (the file must sit next to `manage.py`):

| Setting | Value |
|---|---|
| `DB_*`, `REDIS_*` | defaults from `.env.example` work with docker compose |
| `POLYGON_API_KEY`, `POLYGON_API_SECRET` | from Polygon -> Settings -> API Keys |
| `STORAGE_PROVIDER` | `s3` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_S3_BUCKET_NAME` | your bucket details (the IAM user needs put / list / delete on the bucket) |

The app won't start without the Polygon key and secret.

---

## Step 1: Create a problem on Polygon

Before the tool can do anything, we need a problem on Polygon. Here is what I did for my problem "Who Takes Strike?" (ID `634840`):

1. Create the problem: polygon.codeforces.com -> *New Problem*, give it a name, then open it.
2. General info: time limit 1 second, memory limit 256 MB, input/output from stdin/stdout.
3. Statement: legend, input format, output format and notes (explaining the examples).
4. Checker: I used the standard `std::wcmp.cpp` (compares output word by word).
5. Validator: a small testlib validator that checks the input is six integers between 0 and 6.
6. Solution: uploaded `solution.cpp` and marked it as Main correct solution.
7. Tests: added 14 tests to the testset called `tests`. Tests 1-3 have "Use in statements" ticked, which makes them the samples shown in the statement.
8. Commit changes, then Packages -> Create package (Full) and wait until it shows READY.

Then note two things:

- Problem ID: the number in the *ID* column on the problems list (`634840` for me).
- API key and secret: Settings -> API Keys. These go into `.env`.

> Two things I learned the hard way:
> - The tool only reads the testset named `tests`. My tests were first split across custom testsets (`first_example`, `remaining`, ...), and the tool found 0 tests.
> - The statement is read from the built package, but the tests are read from the live working copy. So after changing the statement you must commit and build a new package, or the tool shows the old one.

---

## Step 2: Log in

Open `http://127.0.0.1:8000/`. You are sent to the Staff Login page.

Enter the email and password of the superuser you created and click Login.

**What happens behind the scenes** (`users/views.py -> login_view`, `users/backends.py -> EmailBackend`)
- The form sends your email and password to `/users/login/`.
- The backend finds the user by email, checks the password, and also checks that the account is staff. Only staff can use the tool.
- If everything is fine, a session is created and you land on the main page (`/`).

**What you see**
- Success -> the migration page with an "Enter Polygon Problem ID" box.
- Wrong password -> "Invalid email or password."
- Not staff -> "You do not have staff access."

**Data:** reads the `users_user` table; writes a session row (you stay logged in for 1 day).

---

## Step 3: Fetch the problem

Type the problem ID (`634840`) and click Fetch Problem. This takes a few seconds because everything comes live from Polygon.

**What the page sends:** just the problem ID, as a form POST to `/`.

**What the backend does** (`problems/views.py -> index`, `problems/polygon_api.py -> PolygonAPI`)
1. Gets the basic problem info from Polygon: time limit, memory limit and so on.
2. Downloads the latest built package (a ZIP), opens `problem.html` inside it, and pulls out the title, statement, input format, output format and notes (`parse_problem_html`).
3. Gets the list of tests in testset `tests`, then downloads the input and answer of every test one by one.
4. Saves those tests in Redis for 30 minutes, so the next buttons don't have to download them again.
5. Gets the checker name (`std::wcmp.cpp` -> shown as `wcmp`).
6. If the problem is already in our database, it also fetches the main correct solution from Polygon.

**What you see**
- Title, slug, a Difficulty dropdown and a Tags picker, time and memory limits, checker type, test count.
- The statement, input format, output format and notes.
- An All Test Cases table with a short preview of each input/output, with the samples marked.
- Main Correct Solution: shown once the problem is in the database (before that it says "Please migrate the problem to the database first").

**Data:** nothing is saved to the database yet. Only Redis gets the cached tests.

---

## Step 4: Migrate the problem to the database

Pick a difficulty (Easy / Medium / Hard), add at least two tags (choose existing ones or type new ones), and click Create/Update problem in Database.

**What the page sends:** problem ID, `migrate_to_db`, the difficulty, and the selected tags.

**What the backend does** (`index`, the `if migrate_to_db:` block)
1. Refreshes the problem data from Polygon (test cases come from the Redis cache).
2. If no difficulty was chosen, it stops with an error.
3. Looks for the problem in the database by its Polygon ID:
   - not there -> creates a new `Problem`
   - already there -> updates it
4. Saves the title, slug, difficulty, statement, input/output format, notes, limits, checker type and test count.
5. Tags: removes the old tags from the problem and attaches the selected ones. New tag names are created on the fly.
6. Samples: takes the tests marked "Use in statements" and saves them as `SampleTestCase` rows (in order 1, 2, 3).
7. Fetches the main correct solution to display.

All of this runs in one database transaction: if anything fails, nothing is saved.

**What you see:** "Problem 'Who Takes Strike?' created in database successfully." The page now shows the Database Problem ID (1 for me), the solution code appears, and the next two buttons are unlocked.

**Data written:** `problems_problem`, `problems_problemtag` (new tags), the problem-tag link table, `problems_sampletestcase`.

---

## Step 5: Migrate test cases to the database

Scroll below the test table and click Migrate Test Description to Database. This is the "Migrate Test Cases to DB" step.

**What the page sends:** problem ID and `migrate_test_cases_to_db`.

**What the backend does** (`index`, the `if migrate_test_cases_to_db:` block)
1. Makes sure the problem is already in the database (otherwise: "Please migrate the problem to the database first.").
2. Takes all tests from the Redis cache (or Polygon, if the cache has expired).
3. For each test, saves a `ProblemTestCase` row with the input, the output, whether it is a sample, the description and its order (`views.py:512-543`). Input and output are cut to the first 260 characters, so these rows are a preview of each test, not the full file.
   - Spaces and newlines at the end of the input and output are removed (`.rstrip()`).
   - A test with an empty input or an empty output is skipped, with no message (`views.py:518`).
4. Re-running it overwrites the existing rows by position (row 1, row 2, ...). It never deletes extra old rows: when my test problem went from 20 tests to 12, the database still had 20 rows (see Q2 in `ISSUES.md`).

**External APIs called:** every click runs the whole fetch from Step 3 again before saving anything (`views.py:189-262`):
- `problem.info` (twice: once directly and once inside the package download)
- `problem.packages` and `problem.package`, which downloads the full package ZIP again
- `problem.checker` (twice: for the checker type and for the custom checker check)
- `problem.tests` (for the test count)
- because the problem is already in the database: `problem.updateWorkingCopy`, `problem.solutions` and `problem.viewSolution` (`views.py:148-183`)
- the test contents come from Redis. If the 30-minute cache has expired, it calls `problem.tests` and then `problem.testInput` and `problem.testAnswer` for every test.

**What you see:** "Test cases description migrated to database Successfully."

**Data written:** `problems_problemtestcase` (14 rows for my problem).

---

## Step 6: Upload test cases to storage

Click Upload Test Cases to Storage.

**What the page sends:** problem ID and `migrate_to_storage`.

**What the backend does** (`index` -> `PolygonAPI.migrate_to_storage` -> `problems/storage/`)
1. Runs the whole fetch from Polygon first (see External APIs below). The upload starts only after all of these calls have worked (`views.py:285-323`), so a Polygon failure leaves the files in storage as they were.
2. Makes sure the problem is in the database and takes its database ID. That ID becomes the folder name.
3. Takes all tests from the Redis cache (or Polygon, if expired).
4. `get_storage()` looks at `STORAGE_PROVIDER=s3` and returns the S3 storage class.
5. Deletes the old folder `test_cases/<id>/` in the bucket, so a re-upload never leaves stale files behind.
6. Uploads each test as two files: the input and the answer (`.a`).
7. If the problem has a custom checker, it is compiled with g++ and uploaded too. Mine uses the standard `wcmp`, so nothing extra.
8. If something fails before the upload (for example, Polygon times out), storage is not touched and the page shows only the error.
9. If the upload itself fails halfway, the files uploaded so far are deleted and you get an error (`views.py:312-317`). Because the old folder was already deleted in step 5, the problem then has no files in storage until you upload again. This is still open (see P2 in `ISSUES.md`).

**External APIs called:**
- Polygon: the same calls as Step 5 (the full fetch, including the package download), plus `problem.checker` once more before the upload. If the Redis cache has expired, the tests are downloaded again (`problem.tests`, `problem.testInput`, `problem.testAnswer`). With a custom checker, its source is downloaded with `problem.viewFile`.
- S3: lists and deletes every object under `test_cases/<id>/`, then uploads two files per test (`put_object`).

**What you see:** "14 test case(s) uploaded to S3 storage under test_cases/1/ successfully."

**Data written:** files in S3 only. The database is only read here.

### How the files are named

```
test_cases/<db_problem_id>/01      # input of test 1
test_cases/<db_problem_id>/01.a    # expected answer of test 1
...
test_cases/<db_problem_id>/14
test_cases/<db_problem_id>/14.a
test_cases/<db_problem_id>/custom_checker   # only if the problem has a custom checker
```

- The folder is the database ID, not the Polygon ID (634840 -> DB id 1 -> `test_cases/1/`).
- Test numbers are two digits (`01`, `02`, ...) so they sort correctly.
- `.a` means *answer*, the usual Polygon/testlib convention.

### Why both the database and storage?

The database is for the website and admin: showing samples on the problem page and browsing tests. The storage files are for the judge: it runs the user's program on `01`, then compares the result with `01.a` using the checker. Test files can be big and many judge machines read them at the same time, so they live in object storage, not in the database.

To use Azure instead, set `STORAGE_PROVIDER=azure` plus the `AZURE_*` values. No code changes are needed.

---

## Polygon API - what we send and what we get back

All calls go to `https://polygon.codeforces.com/api/<method>` as a POST (`PolygonAPI._make_request`).

**Every request carries:**

| Field | Example | Meaning |
|---|---|---|
| `problemId` (+ method params) | `634840` | which problem |
| `apiKey` | your key | who is calling |
| `time` | `1795174692` | current Unix time |
| `apiSig` | `ab12cd` + 128 hex chars | signature |

**How `apiSig` is made** (`_generate_api_sig`): take 6 random characters, then build the string `rand/methodName?sorted_params#secret`, hash it with SHA-512, and send `rand + hash`. The secret itself is never sent; Polygon rebuilds the hash on its side to verify the request.

**Example - `problem.info`**

Request:
```
POST https://polygon.codeforces.com/api/problem.info
problemId=634840&apiKey=...&time=1795174692&apiSig=...
```
Response:
```json
{
  "status": "OK",
  "result": {
    "inputFile": "stdin", "outputFile": "stdout",
    "interactive": false,
    "timeLimit": 1000, "memoryLimit": 256
  }
}
```
If something is wrong you get `{"status": "FAILED", "comment": "..."}` and the page shows that message.

**Example - `problem.tests`** (testset `tests`)
```json
{
  "status": "OK",
  "result": [
    { "index": 1, "manual": true, "useInStatements": true,  "description": "" },
    { "index": 4, "manual": true, "useInStatements": false, "description": "" }
  ]
}
```
Then, for each test, `problem.testInput` and `problem.testAnswer` return plain text, e.g. `1 0 0 0 0 0` and `Venu`.

**All methods the tool uses**

| Method | What we get |
|---|---|
| `problem.info` | limits, input/output files |
| `problem.packages` | list of built packages (we pick the latest one) |
| `problem.package` | the package ZIP (we read `problem.html` from it) |
| `problem.tests` | list of tests and which ones are samples |
| `problem.testInput` / `problem.testAnswer` | input and answer text of one test |
| `problem.checker` | checker name, e.g. `std::wcmp.cpp` |
| `problem.solutions` / `problem.viewSolution` | the main correct solution's source |
| `problem.updateWorkingCopy` | refreshes the working copy before reading solutions |
| `problem.viewFile` | custom checker source (only for custom checkers) |

---

## How to check that everything worked

| What | Where to look |
|---|---|
| Problem, tags, samples, test cases | `http://127.0.0.1:8000/admin/` -> Problems / Problem tags / Sample test cases / Problem test cases |
| What the backend did, step by step | `PolygonMigration/logs/project.log` (try `tail -f`) - shows each Polygon call, cache hits and uploads |
| Cached tests | `docker exec polygon-redis redis-cli keys '*634840*'` |
| Files in storage | AWS console -> S3 -> your bucket -> `test_cases/<db_id>/` - open `01` and `01.a` |
| Storage code without AWS | `python manage.py test problems.test_storage` (8 unit tests with a fake S3 client) |

### Full test run (what I do before a demo)

1. `docker compose up -d` and `python manage.py runserver`
2. Log in -> Fetch `634840` -> the test table shows 14 tests
3. Pick a difficulty and 2 tags -> Create/Update problem in Database -> success message, DB id shown
4. Migrate Test Description to Database -> admin shows 3 samples and 14 test cases
5. Upload Test Cases to Storage -> S3 shows 28 files under `test_cases/<id>/`
6. Open `01` -> `1 0 0 0 0 0`, open `01.a` -> `Venu` (matches sample 1 on the page)
7. Click upload again -> still exactly 28 files

---

## Where to find things in the code

| If you want to change... | Look at |
|---|---|
| login | `users/views.py` (`login_view`), `users/backends.py` (`EmailBackend`) |
| what a button does | `problems/views.py` -> `index()` (one `if` block per button) |
| how the statement is read | `problems/views.py` -> `parse_problem_html()` |
| Polygon calls / signing | `problems/polygon_api.py` -> `_make_request()`, `_generate_api_sig()` |
| the Redis cache | `polygon_api.py` -> `store_test_cases_in_redis()`, `get_test_cases_from_redis()` |
| storage provider or file names | `problems/storage/` (`base.py`, `s3.py`, `__init__.py`) |
| the page itself | `problems/templates/problems/index.html` |
