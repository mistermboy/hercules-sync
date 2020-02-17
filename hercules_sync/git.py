from contextlib import contextmanager
from urllib.parse import urlencode

import base64
import io
import json
import urllib3

from unidiff import PatchSet


GITHUB_BASE_URL = 'https://github.com'
GITHUB_API_URL = 'https://api.github.com'

USER_AGENT = 'weso'

class GitPushEventHandler():
    """ Processes information from a GitHub push event.

    Parameters
    ----------
    data : dict
        Data obtained from a GitHub WebHook regarding a push event.
    """

    def __init__(self, data):
        self.before_commit = data['before']
        self.after_commit = data['after']
        self.repo_name = data['repository']['full_name']
        self.diff_parser = GitDiffParser(self.repo_name,
                                         self.before_commit,
                                         self.after_commit)
        self.data_loader = GitDataLoader(self.repo_name,
                                         self.before_commit,
                                         self.after_commit)

    @property
    def added_files(self):
        """ Files added in the push.

        Returns
        -------
        iterable of :obj: `GitFile`
            Iterable with GitFile objects which contain information
            about each added file.
        """
        added_files = self.diff_parser.patch.added_files
        return self._git_loader_iterator(added_files)

    @property
    def modified_files(self):
        """ Files modified in the push.

        Returns
        -------
        iterable of :obj: `GitFile`
            Iterable with GitFile objects which contain information
            about each modified file.
        """
        modified_files = self.diff_parser.patch.modified_files
        return self._git_loader_iterator(modified_files)

    @property
    def removed_files(self):
        """ Files modified in the push.

        Returns
        -------
        iterable of :obj: `GitFile`
            Iterable with GitFile objects which contain information
            about each modified file.
        """
        removed_files = self.diff_parser.patch.removed_files
        return self._git_loader_iterator(removed_files)

    def _git_loader_iterator(self, patched_files):
        for gitfile in self.data_loader.load_files(patched_files):
            yield gitfile

class GitFile():
    """ Encapsulates the content of a file and the git diff information.

    Parameters
    ----------
    patched_file : :obj:`unidiff.PatchFile`
        PatchFile instance.
    source_content : str
        Original content of the file before the push (source).
    target_content : str
        Final content of the file after the push (target).
    """

    def __init__(self, patched_file, source_content, target_content):
        self._patched_file = patched_file
        self.source_content = source_content
        self.target_content = target_content

    @property
    def file_path(self):
        return self._patched_file.path

    @property
    def added_lines(self):
        """

        Returns
        -------
        list of (str, int)
            List of tuples where each tuple contains the content of the added
            line and the number of the line in the target file.
        """
        return [(line.value, line.target_line_no)
                for hunk in self._patched_file
                for line in hunk if line.is_added]

    @property
    def removed_lines(self):
        """

        Returns
        -------
        list of (str, int)
            List of tuples where each tuple contains the content of the removed
            line and the number of the line in the source file.
        """
        return [(line.value, line.source_line_no)
                for hunk in self._patched_file
                for line in hunk if line.is_removed]

    def _get_lines(self, line_filter):
        return [(line.value, line.target_line_no)
                for hunk in self._patched_file
                for line in hunk if line_filter(line)]


class GitDiffParser():
    """ Return Diff information from a repository.

    Parameters
    ----------
    repo_full_name : str
        Full name of the github repository (must follow the
        form 'user_name/repo_name').
    before_commit : str
        Sha of the initial commit before the push.
    after_ref : str
        Sha of the final commit after the push.
    """

    def __init__(self, repo_full_name, before_commit, after_commit):
        self.compare_url = self._build_compare_url(repo_full_name,
                                                   before_commit,
                                                   after_commit)
        self.load_diff()
        self._assert_valid_data()

    def load_diff(self):
        """

        Returns
        -------
        :obj: `unidiff.PatchSet`
            PatchSet instance with the diff information.
        """
        http = urllib3.PoolManager()
        print(self.compare_url)
        req = http.request(
            'GET',
            self.compare_url,
            headers={
                'User-Agent': USER_AGENT
            }
        )
        # TODO: parse response status
        diff = req.data.decode("utf-8")
        self.patch = PatchSet(diff)

    def _build_compare_url(self, repo_name, before_commit, after_commit):
        return '{0}/{1}/{2}/{3}...{4}.diff'.format(GITHUB_BASE_URL, repo_name, 'compare',
                                                   before_commit, after_commit)

    def _assert_valid_data(self):
        # TODO
        pass

class GitDataLoader():
    """ Downloads github files from a commit, before and after a push.

    This class is used to download files from a github repository given a certain
    original (before_ref) and final commit (after_ref).

    Parameters
    ----------
    repo_name : str
        Full name of the github repository where the files are located.
    before_ref : str
        Sha of the initial commit before the push.
    after_ref : str
        Sha of the final commit after the push.
    """

    def __init__(self, repo_name, before_ref, after_ref):
        self.repo_name = repo_name
        self.before_ref = before_ref
        self.after_ref = after_ref

    def load_files(self, files_to_load):
        """ Downloads the given files, returning them inside GitFile objects.

        Parameters
        ----------
        files_to_load : list of :obj:`unidiff.PatchFile`
            Iterable containing instances of patchfile objects.

        Yields
        -------
        :obj:`GitFile`
            Generator that returns one instance of the GitFile class for each
            downloaded file from GitHub.
        """
        http = urllib3.PoolManager()
        return (GitFile(patched_file,
                        self._load_file(patched_file.path, http, self.before_ref),
                        self._load_file(patched_file.path, http, self.after_ref))
                for patched_file in files_to_load)

    def _load_file(self, file_path, http, ref):
        # TODO: what happens if the file doesn't exist?
        # e.g. deleted file wont be available in after_ref, added wont in before_ref
        # IMO an empty string should be returned

        args = urlencode({'ref': ref})
        download_url = '{0}/repos/{1}/contents/{2}?{3}'.format(
            GITHUB_API_URL, self.repo_name, file_path, args)
        req = http.request(
            'GET',
            download_url,
            headers={
                'User-Agent': USER_AGENT
            }
        )

        content = json.loads(req.data.decode('utf-8'))['content']
        decoded_content = base64.b64decode(content).decode('utf-8')
        return decoded_content
