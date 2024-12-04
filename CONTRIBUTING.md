# Contributing

Welcome to `vptstools` contributor's guide.

This document focuses on getting any potential contributor familiarized with the development processes, but [other kinds of contributions] are also appreciated.

If you are new to using [git] or have never collaborated in a project previously, please have a look at [contribution-guide.org].

Please notice, all users and contributors are expected to be **open,
considerate, reasonable, and respectful**. When in doubt,
[Python Software Foundation's Code of Conduct] is a good reference in terms of behavior guidelines.

## Issue Reports

If you experience bugs or general issues with `vptstools`, please have a look on the [issue tracker]. If you don't see anything useful there, please feel free to fire an issue report.

:::{tip}
Please don't forget to include the closed issues in your search.
Sometimes a solution was already reported, and the problem is considered **solved**.
:::

New issue reports should include information about your programming environment (e.g., operating system, Python version) and steps to reproduce the problem. Please try also to simplify the reproduction steps to a very minimal example that still illustrates the problem you are facing. By removing other factors, you help us to identify the root cause of the issue.

## Documentation Improvements

You can help improve `vptstools` docs by making them more readable and coherent, or by adding missing information and correcting mistakes.

`vptstools` documentation uses [Sphinx] as its main documentation compiler. This means that the docs are kept in the same repository as the project code, and that any documentation update is done in the same way was a code contribution.

The syntax used for the documentation is [CommonMark] with [MyST] extensions.

:::{tip}
   Please notice that the [GitHub web interface] provides a quick way of propose changes in `vptstools`'s files. While this mechanism can
   be tricky for normal code contributions, it works perfectly fine for contributing to the docs, and can be quite handy.

   If you are interested in trying this method out, please navigate to
   the `docs` folder in the source [repository], find which file you
   would like to propose changes and click in the little pencil icon at the top, to open [GitHub's code editor]. Once you finish editing the file, please write a message in the form at the bottom of the page describing which changes have you made and what are the motivations behind them and submit your proposal.
:::

When working on documentation changes in your local machine, you can
compile them using [tox] :

```
tox -e docs
```

and use Python's built-in web server for a preview in your web browser
(`http://localhost:8000`):

```
python3 -m http.server --directory 'docs/_build/html'
```

## Code Contributions

The code is used both as a library to handle VPTS files (hdf5, csv,...) as well as the cli functionality to run the data processing services (conversion of files, updates of the Bucket,...).

### Submit an issue

Before you work on any non-trivial code contribution it's best to first create a report in the [issue tracker] to start a discussion on the subject. This often provides additional considerations and avoids unnecessary work.

### Setup an environment

1. Create an user account on GitHub if you do not already have one.

2. Fork the project [repository]: click on the *Fork* button near the top of the page. This creates a copy of the code under your account on GitHub.

3. Clone this copy to your local disk:

   ```
   git clone git@github.com:YourLogin/vptstools.git
   cd vptstools
   ```

4. Before you start coding, we recommend creating an isolated `virtual environment`_ to avoid any problems with your installed Python packages. This can be done via either [virtualenv]:

   ```
   python3 -m venv <ENVIRONMENT-NAME>
   source <ENVIRONMENT-NAME>/bin/activate
   ```

4. You should run:

   ```
   pip install -U pip setuptools -e .[develop,transfer]
   ```

   to be able to import the package under development in the Python REPL and installing the required development dependencies.

:::{tip}
   If you have |tox|_:: installed, you can use tox to create your development environment containing both the package dependencies and development requirements::

   ```
   tox -e dev
   ```
:::

### Implement your changes

1. Create a branch to hold your changes:

   ```
   git checkout -b my-feature
   ```

   and start making changes. Never work on the main branch!

2. Start your work on this branch. Don't forget to add [docstrings] to new
   functions, modules and classes, especially if they are part of public APIs.

3. Add yourself to the list of contributors in `AUTHORS.md`.

4. When you’re done editing, do:

   ```
   git add <MODIFIED FILES>
   git commit
   ```

   to record your changes in [git].

   :::{important}
   Don't forget to add unit tests and documentation in case your
   contribution adds an additional feature and is not just a bugfix.

   Moreover, writing a [descriptive commit message] is highly recommended.
   In case of doubt, you can check the commit history with:

   ```
   git log --graph --decorate --pretty=oneline --abbrev-commit --all
   ```

   to look for recurring communication patterns.
   :::

5. Please check that your changes don't break any unit tests with:

   ```
   tox
   ```

   (after having installed [tox] with `pip install tox` or `pipx`).

   You can also use [tox] to run several other pre-configured tasks in the
   repository. Try `tox -av` to see a list of the available checks.

### Submit your contribution

1. If everything works fine, push your local branch to the remote server with:

   ```
   git push -u origin my-feature
   ```

2. Go to the web page of your fork and click "Create pull request"
   to send your changes for review.

   Find more detailed information in [creating a PR]. You might also want to open
   the PR as a draft first and mark it as ready for review after the feedbacks
   from the continuous integration (CI) system or any required fixes.

### Troubleshooting

The following tips can be used when facing problems to build or test the
package:

1. Make sure to fetch all the tags from the upstream [repository].
   The command `git describe --abbrev=0 --tags` should return the version you
   are expecting. If you are trying to run CI scripts in a fork repository,
   make sure to push all the tags.
   You can also try to remove all the egg files or the complete egg folder, i.e.,
   `.eggs`, as well as the `*.egg-info` folders in the `src` folder or
   potentially in the root of your project.

2. Sometimes [tox] misses out when new dependencies are added, especially to
   `setup.cfg` and `docs/requirements.txt`. If you find any problems with
   missing dependencies when running a command with [tox], try to recreate the
   `tox` environment using the `-r` flag. For example, instead of:

   ```
   tox -e docs
   ```

   Try running:

   ```
   tox -r -e docs
   ```

3. Make sure to have a reliable [tox] installation that uses the correct
   Python version (e.g., 3.7+). When in doubt you can run:

   ```
   tox --version
   # OR
   which tox
   ```

   If you have trouble and are seeing weird errors upon running [tox], you can also try to create a dedicated [virtual environment] with a [tox] binary freshly installed. For example:

   ```
   virtualenv .venv
   source .venv/bin/activate
   .venv/bin/pip install tox
   .venv/bin/tox -e all
   ```

4. [Pytest can drop you] in an interactive session in the case an error occurs.
   In order to do that you need to pass a `--pdb` option (for example by
   running `tox -- -k <NAME OF THE FALLING TEST> --pdb`).
   You can also setup breakpoints manually instead of using the `--pdb` option.

## Maintainer tasks

### Releases

Github Actions is used to automatic push releases to pypi by the publish step in `release.yml`. To create a new release:

- `git checkout main`, `git pull origin main`
- Update the `CHANGELOG.md` with the changes for this new release
- `git commit -m 'Update changelog for release  X.X.X' CHANGELOG.md
- `git push origin master`
- Add git tags: `git tag vX.X.X` 
- Push the git tags: `git push --tags`
- On the [release page](https://github.com/aloftdata/vptstools/releases) draft a new release using the latest git tag
- Copy past the changes from the changelog in the dialog and publish release
- Check if Github Actions runs the deployment of docs and pypi

If it would be required ( and if you have correct user permissions on [PyPI]) the last step to publish a new version 
for `vptstools` to pypi can be done manually as well with the following steps:

1. Make sure all unit tests are successful.
2. Clean up the `dist` and `build` folders with `tox -e clean`
   (or `rm -rf dist build`)
   to avoid confusion with old builds and Sphinx docs.
3. Run `tox -e build` and check that the files in `dist` have
   the correct version (no `.dirty` or [git] hash) according to the [git] tag. Also check the sizes of the distributions, if they are too big (e.g., >
   500KB), unwanted clutter may have been accidentally included.
4. Run `tox -e publish -- --repository pypi` and check that everything was uploaded to [PyPI] correctly.

(new-vptscsv-version)=
### Support a new version of the VPTS-CSV data exchange format

To support a new version of the VPTS-CSV data exchange format, following adjustments in the {py:mod}`vptstools.vpts_csv` 
module are required:

- Create a new class `VptsCsvVX` which subclasses from the abstract class {py:class}`vptstools.vpts_csv.AbstractVptsCsv`
- Overwrite the abstract methods to define 'no data' representation, the 'Undetect' representation, the sorting logic 
  and the mapping of the individual fields from ODIM bird profile to the VPTS CSV data format. Check the
  {py:class}`vptstools.vpts_csv.AbstractVptsCsv` documentation for more info.
- Link the string version ID (v1, v2,..) with the correct `AbstractVptsCsv` child class by extending the 
  {py:func}`vptstools.vpts_csv.get_vpts_version` with a new mapping from version string to class instance. 
- Add the string version to the unit test in the ``@pytest.mark.parametrize("vpts_version", ["v1.0", "vX.X])`` so these
  existing unit tests are also checked for the new version.


[black]: https://pypi.org/project/black/
[commonmark]: https://commonmark.org/
[contribution-guide.org]: http://www.contribution-guide.org/
[creating a pr]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request
[descriptive commit message]: https://chris.beams.io/posts/git-commit
[docstrings]: https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html
[first-contributions tutorial]: https://github.com/firstcontributions/first-contributions
[flake8]: https://flake8.pycqa.org/en/stable/
[git]: https://git-scm.com
[github web interface]: https://docs.github.com/en/github/managing-files-in-a-repository/managing-files-on-github/editing-files-in-your-repository
[github's code editor]: https://docs.github.com/en/github/managing-files-in-a-repository/managing-files-on-github/editing-files-in-your-repository
[github's fork and pull request workflow]: https://guides.github.com/activities/forking/
[myst]: https://myst-parser.readthedocs.io/en/latest/syntax/syntax.html
[other kinds of contributions]: https://opensource.guide/how-to-contribute
[pypi]: https://pypi.org/
[pyscaffold's contributor's guide]: https://pyscaffold.org/en/stable/contributing.html
[pytest can drop you]: https://docs.pytest.org/en/stable/how-to/failures.html?highlight=pdb#dropping-to-pdb-on-failures
[python software foundation's code of conduct]: https://www.python.org/psf/conduct/
[restructuredtext]: https://www.sphinx-doc.org/en/master/usage/restructuredtext/
[sphinx]: https://www.sphinx-doc.org/en/master/
[tox]: https://tox.readthedocs.io/en/stable/
[virtual environment]: https://realpython.com/python-virtual-environments-a-primer/
[virtualenv]: https://docs.python.org/3/library/venv.html


[repository]: https://github.com/aloftdata/vptstools
[issue tracker]: https://github.com/aloftdata/vptstools/issues
