"""
Provider-agnostic interface for test-case storage.

The migration flow (PolygonAPI.migrate_to_storage) depends only on this
interface. Each cloud provider implements it in its own module, and
get_storage() in __init__.py picks one based on settings.STORAGE_PROVIDER.

Object key layout (shared by every provider, defined only here):
    test_cases/{problem_id}/{NN}       test input   (NN = zero-padded test number)
    test_cases/{problem_id}/{NN}.a     expected output
    test_cases/{problem_id}/<name>     extra files, e.g. the compiled custom checker
"""
from abc import ABC, abstractmethod

KEY_ROOT = "test_cases"


def problem_prefix(problem_id):
    """Prefix under which all files of one problem live, e.g. 'test_cases/7/'."""
    return f"{KEY_ROOT}/{problem_id}/"


def test_input_key(problem_id, test_number):
    """Key of a test's input file, e.g. 'test_cases/7/01'."""
    return f"{problem_prefix(problem_id)}{test_number:02d}"


def test_output_key(problem_id, test_number):
    """Key of a test's expected-output file, e.g. 'test_cases/7/01.a'."""
    return f"{test_input_key(problem_id, test_number)}.a"


def problem_file_key(problem_id, filename):
    """Key of an extra per-problem file, e.g. 'test_cases/7/custom_checker'."""
    return f"{problem_prefix(problem_id)}{filename}"


class TestCaseStorage(ABC):
    """
    Abstract storage backend for test cases.

    Implementations must raise an exception when an operation fails, so the
    caller can report the error instead of showing a false success.
    """

    #: Short human-readable provider name used in logs and UI messages.
    display_name = "storage"

    @abstractmethod
    def upload_file(self, key, data):
        """
        Upload raw bytes to the given object key, overwriting any existing object.

        Args:
            key (str): Full object key, e.g. 'test_cases/7/01'.
            data (bytes): File contents.
        """

    @abstractmethod
    def delete_problem_files(self, problem_id):
        """
        Delete every object under test_cases/{problem_id}/.

        Args:
            problem_id (str|int): Database problem ID used in the key prefix.

        Returns:
            int: Number of objects deleted.
        """

    def upload_test_case(self, problem_id, test_number, input_data, output_data):
        """
        Upload one test case as two objects: input ({NN}) and expected output ({NN}.a).

        Args:
            problem_id (str|int): Database problem ID used in the key prefix.
            test_number (int): 1-based test number.
            input_data (str): Test input.
            output_data (str): Expected output.
        """
        self.upload_file(test_input_key(problem_id, test_number), input_data.encode("utf-8"))
        self.upload_file(test_output_key(problem_id, test_number), output_data.encode("utf-8"))
