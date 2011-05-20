#!/usr/bin/env python3
#
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# For more information, please refer to <http://unlicense.org/>
#
"""DVCS View

This tool helps to get an overview of the status of Git and Mercurial
repositories. The script searches for all repos in your workspaces and prints
a short status overview. It checks for uncommited changes in the working
directory and if configured pull/push-repos are in sync.

[DVCS View](http://github.com/samuelspiza/dvcsview) is hosted on Github.

The [template](http://gist.github.com/258034) contains examples for the
configuration of DVCS View.
"""

__author__ = "Samuel Spiza <sam.spiza@gmail.com>"
__version__ = "0.3.1"

import re
import os
import configparser
import optparse
from subprocess import call, Popen, PIPE
import sys
import logging

CONFIG_FILENAMES = [os.path.expanduser("~/.dvcsview.conf"),
                    os.path.dirname(os.path.abspath((__file__))) + \
                    "dvcsview.conf",
                    os.path.expanduser("~/dvcsview.ini"),
                    os.path.dirname(os.path.abspath((__file__))) + \
                    "dvcsview.ini"]
DEFAULT_LOGGER = "dvcsview"
SETTINGS = "settings"
WORKSPACES = "workspaces"
REPOS = "repos"

def getOptions(argv):
    parser = optparse.OptionParser()
    parser.add_option("-t", "--targets",
                      dest="targets", metavar="HOSTS", default="",
                      help="Pull/push-repos on these hosts will be checked if "
                           "they are in sync. Argument is a comma separated "
                           "list of the hosts. Hosts can be IPv4-addresses or "
                           "domains. Windows volume letters (e.g. 'c:') and "
                           "1st level folder in the root directory "
                           "(e.g. '/home') in Linux systems are possible too. "
                           "Alias can be configured in '.dvcsview.conf'.")
    parser.add_option("-q", "--quiet",
                      dest="quiet", action="store_true", default=False,
                      help="Only one line per repository.")
    return parser.parse_args(argv)[0]

def getWorkspaces(config):
    """Returns all existing workspaces from the config."""
    logger = logging.getLogger(DEFAULT_LOGGER)
    ret = []
    for w in config.items(WORKSPACES):
        workspace = os.path.expanduser(w[1])
        if os.path.exists(workspace):
            ret.append(workspace)
        else:
            logger.warning("Workspace '%s' does not exist." % workspace)
    return ret

def findRepos(path, repos, targets=[], skip=[]):
    """Populates 'repos' recursively.
    
    Calls itself for all directories of the dirlist reduced by 'addRepo'.
    """
    entries = addRepo(path, repos, targets=targets, skip=skip)
    for entry in entries:
        newpath = os.path.join(path, entry)
        if os.path.isdir(newpath):
            findRepos(newpath, repos, targets=targets, skip=skip)

def addSingleRepo(path, repos, targets=[], skip=[]):
    """Instanciates a subclass of 'Repo' if 'path' is a repository."""
    logger = logging.getLogger(DEFAULT_LOGGER)
    if not os.path.exists(path):
        logger.warning("Repository '%s' does not exist." % path)
        return
    # Check if the repository was already found while walking throug the
    # workspaces.
    for repo in repos:
        if path == repo.path:
            logger.info("Repository '%s' is in a workspace." % path)
            return
    addRepo(path, repos, targets=targets, skip=skip)

def addRepo(path, repos, targets=[], skip=[]):
    """Checks if 'path' is a repo and creates Repo objects.
    
    If path contains one of the DVCS specific hidden repository directories,
    the corresponding subclass of Repo will be instanciated. This object is
    appended to 'repos'. Returns the dirlist of 'path' without this directory.
    """
    entries = os.listdir(path)
    if ".git" in entries and not "git" in skip:
        repos.append(Git(path, targets=targets))
        entries.remove(".git")
    elif ".hg" in entries and not "hg" in skip:
        repos.append(Hg(path, targets=targets))
        entries.remove(".hg")
    return entries

class WrappedFile:
    """File object that returns all lines striped on the left."""
    def __init__(self, path):
        self.file = open(path, "r")

    def __iter__(self):
        return self.file.__iter__()

    def readline(self):
        return self.file.readline().lstrip()

class Repo:
    def __init__(self, path, targets=[]):
        self.path = path
        os.chdir(self.path)
        self.targets = targets
        self.config = self.getConfig()
        ipseg = "[12]?[0-9]{1,2}"
        ip = "(?<=@)(?:" + ipseg + "\.){3}" + ipseg + "(?=[:/])"
        url = "(?<=[/@\.])[a-z0-9-]*\.(?:com|de|net|org)(?=[:/])"
        d = "^(?:/[a-z]+(?=/)|[a-z]:)"
        regexp = "|".join([ip, url, d])
        self.re = re.compile(regexp)
        self.fetch()
        self.status = None
        self.statusString = None
        self.warningsString = None
        # Must be called (now) because getStatus doesn't change the current
        # working directory.
        self.getStatus()

    def getConfig(self):
        config = None
        if os.path.exists(self.configFile):
            config = configparser.ConfigParser()
            config.readfp(open(self.configFile))
        return config

    def fetch(self):
        logger = logging.getLogger(DEFAULT_LOGGER)
        for r in self.getRemotes():
            m = self.re.search(r['url'])
            if m is not None and self.targets.check(m.group(0)):
                logger.info("fetch %s (%s)" % (r['url'], r['comment']))
                self.fetchRemote(r)

    def pipe(self, command):
        pipe = Popen(command, shell=True, stdout=PIPE).stdout
        return [l.decode().strip() for l in pipe.readlines()]

    def getWarnings(self, status):
        count = [[c, 0] for c in self.count]
        mod = []
        for line in status:
            if line not in self.skip:
                for rep in self.replace:
                    line = re.sub(rep[0], rep[1], line)
                a = False
                for i in range(len(count)):
                    m = re.search(count[i][0][0], line)
                    if m is not None:
                        count[i][1] += 1
                        a = True
                if not a:
                    mod.append(line)
        for c in count:
            if 0 < c[1]:
                if 1 == c[1]:
                    mod[0:0] = ["# %s: 1 file" % c[0][1]]
                else:
                    mod[0:0] = ["# %s: %s files" % (c[0][1], c[1])]
        return mod

    def getStatusString(self):
        if self.statusString is None:
            if self.isClean():
                isClean = "CLEAN    "
            else:
                isClean = "NOT CLEAN"
            self.statusString = "%s %s %s" % (isClean, self.typ, self.path)
        return self.statusString

    def getWarningsString(self):
        if self.warningsString is None:
            self.warningsString = "\n  ".join(self.getWarnings())
        return self.warningsString

class Git(Repo):
    typ = "Git"
    configFile = ".git/config"
    count = []
    count.append(["^#\t(?![a-z ]*:)","untracked"])
    count.append(["^#\tdeleted:", "deleted"])
    count.append(["^#\trenamed:", "renamed"])
    count.append(["^#\tmodified:", "modified"])
    count.append(["^#\tnew file:", "new file"])
    replace = [("Your branch is ahead of '\w*/\w*' by ([0-9]* commits?).",
                "ahead: \g<1>"),
               ("Changes to be committed:", "Changes to be committed")]
    skip = ["# Changed but not updated:", "# Untracked files:"]

    def __init__(self, path, targets=[]):
        self.trackingbranches = None
        Repo.__init__(self, path, targets=targets)

    def getConfig(self):
        config = configparser.ConfigParser()
        config.readfp(WrappedFile(self.configFile))
        return config

    def fetchRemote(self, r):
        call(r['cmd'], shell=True)

    def getRemotes(self):
        remotesections = [s for s in self.config.sections()
                          if s.startswith("remote")]
        remotes = []
        for r in remotesections:
            remotes.append({'cmd': "git fetch " + r[8:-1],
                            'url': self.config.get(r, "url"),
                            'comment': r[8:-1]})
        return remotes

    def getStatus(self):
        if self.status is None:
            self.status = self.buildStatus()
        return self.status

    def buildStatus(self):
        if self.trackingbranches is None:
            self.trackingbranches = self.getTrackingBranches()
        status = self.pipe("git status")
        self.trackingbranches[status[0][12:]] = status
        return status

    def getTrackingBranches(self):
        branches = [s for s in self.config.sections()
                      if s.startswith("branch")]
        return dict([(b[8:-1], None) for b in branches
                     if self.config.has_option(b, "merge")])

    def isClean(self):
        b = self.getStatus()[-1][:17] == "nothing to commit"
        if b:
            self.allBranches()
        return b

    def allBranches(self):
        status = self.getStatus()
        defaultbranch = status[0][12:]
        for b in self.trackingbranches.items():
            if b[0] != status[0][12:]:
                call("git checkout %s" % b[0], shell=True)
                status = self.getStatus()
        if status[0][12:] != defaultbranch:
            call("git checkout %s" % defaultbranch, shell=True)

    def getWarnings(self):
        warnings = []
        for status in self.trackingbranches.values():
            if status is not None:
                mod = Repo.getWarnings(self, status[1:])
                warn = ["  %s" % s for s in mod
                        if s.startswith("# ") and not s[1:].startswith("  ")]
                if 0 < len(warn):
                    warn[0:0] = ["# %s" % status[0][5:]]
                    warnings.extend(warn)
        return warnings

class Hg(Repo):
    typ = "Hg "
    configFile = ".hg/hgrc"
    count = [("^\?", "?"), ("^M", "M")]
    replace = []
    skip = []

    def __init__(self, path, targets=[]):
        self.inout = []
        Repo.__init__(self, path, targets=targets)

    def getRemotes(self):
        remotes = []
        if self.config is not None and self.config.has_option("paths", 'default'):
            default = self.config.get("paths", "default")
            remotes.extend([{'cmd': "hg incoming",
                             'url': default,
                             'comment': "incoming"},
                            {'cmd': "hg outgoing",
                             'url': default,
                             'comment': "outgoing"}])
            if self.config.has_option("paths", 'default-push'):
                remotes[1]['url'] = self.config.get("paths", "default-push")
        return remotes

    def fetchRemote(self, r):
        s = len([l for l in self.pipe(r['cmd']) if l.startswith("changeset")])
        if 0 < s:
            self.inout.append("# %s: %s changesets" % (r['cmd'][3:], s))

    def getStatus(self):
        if self.status is None:
            self.status = self.pipe("hg status")
        return self.status

    def isClean(self):
        return 0 == len(self.getStatus())

    def getWarnings(self):
        return Repo.getWarnings(self, self.getStatus()) + self.inout

class Targets:
    SEP = ","
    SECTION = "alias"

    def __init__(self, list):
        self.list = list
        self.read()
        self.readAlias()
        self.resolvedList = self.resolveList(self.list)

    def read(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILENAMES)
        if not config.has_section(self.SECTION):
            config.add_section(self.SECTION)
        self.config = config

    def readAlias(self):
        ops = self.config.options(self.SECTION)
        self.alias = dict([(o, self.config.get(self.SECTION, o)) for o in ops])

    def resolveList(self, list):
        list, alias = self._resolveList(list, dict(self.alias))
        return list

    def _resolveList(self, list, alias):
        ret = []
        splited = [e.strip() for e in list.split(self.SEP)]
        for e in splited:
            if e in alias:
                f = alias[e]
                alias[e] = ""
                e, alias = self._resolveList(f, alias)
            else:
                e = [e]
            for g in e:
                if g != "" and not g in ret:
                    ret.append(g)
        return ret, alias

    def check(self, url):
        if self.list == "":
            return False
        if self.isNew(url):
            self.promtUser(url)
        return self.isInList(url)

    def isNew(self, url):
        return not url in self.resolveList(self.SEP.join(self.alias.keys()))

    def promtUser(self, url):
        keys = self.alias.keys()
        if 0 < len(keys):
            print("Current alias:")
            out = keys[0]
            for alias in keys[1:]:
                if 80 < len(out + ", " + alias):
                    print(out)
                    out = alias
                else:
                    out += ", " + alias
            print(out)
        out = "add '%s' to alias (list alias seperated by '%s'):\n"
        addTo = input(out % (url, self.SEP))
        addToList = set([e.strip() for e in addTo.split(self.SEP)])
        for alias in addToList:
            if self.config.has_option(self.SECTION, alias):
                self.config.set(self.SECTION, alias,
                                self.config.get(self.SECTION, alias) + \
                                self.SEP + url)
            else:
                self.config.set(self.SECTION, alias, url)
        self.write()
        self.readAlias()
        self.resolvedList = self.resolveList(self.list)

    def write(self):
        for path in reversed(CONFIG_FILENAMES):
            if os.path.exists(path):
                self.config.write(open(path, 'w'))

    def isInList(self, url):
        return url in self.resolvedList

def main(argv):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILENAMES)

    options = getOptions(argv)

    # Configure the logging.
    logging.getLogger().setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    if options.quiet:
        handler.setLevel(logging.WARNING)
    else:
        handler.setLevel(logging.DEBUG)
    format = "%(levelname)-8s %(message)s"
    handler.setFormatter(logging.Formatter(format))
    logging.getLogger().addHandler(handler)

    targets = Targets(options.targets)

    # Parse the VCSs that shall be skipped.
    skip = []
    if config.has_section(SETTINGS):
        for opt in config.options(SETTINGS):
            if opt.startswith("skip.") and config.getboolean(SETTINGS, opt):
                skip.append(opt[5:])

    repos = []

    if config.has_section(WORKSPACES):
        workspaces = getWorkspaces(config)
        for workspace in workspaces:
            findRepos(workspace, repos, targets=targets, skip=skip)

    if config.has_section(REPOS):
        singlerepos = config.items(REPOS)
        for path in singlerepos:
            addSingleRepo(path[1], repos, targets=targets, skip=skip)

    for repo in repos:
        print(repo.getStatusString())
        if not options.quiet:
            warningsString = repo.getWarningsString()
            if 0 < len(warningsString):
                print(warningsString)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
