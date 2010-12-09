#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
__version__ = "0.2.1"

import re
import os
import ConfigParser
import optparse
from subprocess import call, Popen, PIPE
import sys

CONFIG_FILENAMES = [os.path.expanduser("~/.dvcsview.conf"), "dvcsview.conf",
                    os.path.expanduser("~/dvcsview.ini"), "dvcsview.ini"]
SETTINGS = "settings"
WORKSPACES = "workspaces"
REPOS = "repos"
ALIAS = "alias"

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
    workspaces = [os.path.expanduser(w[1]) for w in config.items(WORKSPACES)]
    for w in workspaces[:]:
        if not os.path.exists(w):
            print "ERROR: Workspace '%s' does not exist.\n" % w
            workspaces.remove(w)
    return workspaces

def findRepos(path, repos, targets=[], skip=[], quiet=False):
    entries = addRepo(path, repos, targets=targets, skip=skip, quiet=quiet)
    for entry in entries:
        newpath = os.path.join(path, entry)
        if os.path.isdir(newpath):
            findRepos(newpath, repos, targets=targets, skip=skip, quiet=quiet)

def addSingleRepo(path, repos, targets=[], skip=[], quiet=False):
    if not os.path.exists(path):
        print "ERROR: Repository '%s' does not exist.\n" % path
        return
    for repo in repos:
        if path == repo.path:
            print "ERROR: Repository '%s' is in a workspace.\n" % path
            return
    addRepo(path, repos, targets=targets, skip=skip, quiet=quiet)

def addRepo(path, repos, targets=[], skip=[], quiet=False):
    entries = os.listdir(path)
    if ".git" in entries and not "git" in skip:
        repos.append(Git(path, targets=targets, quiet=quiet))
        entries.remove(".git")
    elif ".hg" in entries and not "hg" in skip:
        repos.append(Hg(path, targets=targets, quiet=quiet))
        entries.remove(".hg")
    return entries

class WrappedFile:
    def __init__(self, path):
        self.file = open(path, "r")

    def readline(self):
        return self.file.readline().lstrip()

class Repo:
    def __init__(self, path, targets=[], quiet=False):
        self.path = path
        os.chdir(self.path)
        self.targets = targets
        self.quiet = quiet
        self.config = self.getConfig()
        ipseg = "[12]?[0-9]{1,2}"
        ip = "(?<=@)(?:" + ipseg + "\.){3}" + ipseg + "(?=[:/])"
        url = "(?<=[/@\.])[a-z0-9-]*\.(?:com|de|net|org)(?=[:/])"
        d = "^(?:/[a-z]+(?=/)|[a-z]:)"
        regexp = "|".join([ip, url, d])
        self.re = re.compile(regexp)
        self.fetch()
        self.statusstring = self.buildStatusString()

    def getConfig(self):
        config = None
        if os.path.exists(self.configFile):
            config = ConfigParser.ConfigParser()
            config.readfp(open(self.configFile))
        return config

    def fetch(self):
        for r in self.getRemotes():
            m = self.re.search(r['url'])
            if m is not None and m.group(0) in self.targets:
                print "fetch %s (%s)" % (r['url'], r['comment'])
                self.fetchRemote(r)

    def buildStatusString(self):
        status = self.getStatus()
        if self.isClean(status):
            isClean = "CLEAN    "
        else:
            isClean = "NOT CLEAN"
        text = self.path
        if not self.quiet:
            text = "\n  ".join([text] + self.getWarnings(status))
        return "%s %s %s" % (isClean, self.typ, text)

    def pipe(self, command):
        pipe = Popen(command, shell=True, stdout=PIPE).stdout
        return [l.strip() for l in pipe.readlines()]

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

    def __init__(self, path, targets=[], quiet=False):
        self.trackingbranches = None
        Repo.__init__(self, path, targets=targets, quiet=quiet)

    def getConfig(self):
        config = ConfigParser.ConfigParser()
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

    def isClean(self, status):
        b = status[-1][:17] == "nothing to commit"
        if b:
            self.allBranches(status)
        return b

    def allBranches(self, status):
        defaultbranch = status[0][12:]
        for b in self.trackingbranches.items():
            if b[0] != status[0][12:]:
                call("git checkout %s" % b[0], shell=True)
                status = self.getStatus()
        if status[0][12:] != defaultbranch:
            call("git checkout %s" % defaultbranch, shell=True)

    def getWarnings(self, status):
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

    def __init__(self, path, targets=[], quiet=False):
        self.inout = []
        Repo.__init__(self, path, targets=targets, quiet=quiet)

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
            self.inout.append("# %s: %s changesets" % (cmd[3:], s))

    def getStatus(self):
        return self.pipe("hg status")

    def isClean(self, status):
        return 0 == len(status)

    def getWarnings(self, status):
        return Repo.getWarnings(self, status) + self.inout

def main(argv):
    config = ConfigParser.ConfigParser()
    config.read(CONFIG_FILENAMES)

    options = getOptions(argv)

    targets = options.targets
    # replace fetch alias with configured hosts
    if config.has_section(ALIAS):
        for opt in config.options(ALIAS):
            if targets == opt:
                targets = config.get(ALIAS, opt)
    # split comma separated list and strip elements
    targets = [t.strip() for t in targets.split(',') if 0 < len(t.strip())]

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
            # creates 'Git' or 'Hg' objects and appends them to 'repos'
            findRepos(workspace, repos, targets=targets, skip=skip,
                      quiet=options.quiet)

    if config.has_section(REPOS):
        singlerepos = config.items(REPOS)
        for path in singlerepos:
            # creates 'Git' or 'Hg' objects and appends them to 'repos'
            addSingleRepo(path[1], repos, targets=targets, skip=skip,
                          quiet=options.quiet)

    for repo in repos:
        print repo.statusstring

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
