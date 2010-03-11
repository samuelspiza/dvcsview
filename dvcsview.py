#!/usr/bin/env python

"""
dvcsview - prints status summary for DVCS repositories

This tool helps to get an overview of the status of Git and Mercurial 
repositories. The script searches for all repos in your workspaces and prints
a short status overview. It checks for uncommited changes in the working 
directory and if configured pull/push-repos are in sync.

Dvcsview is hosted on Github. Checkout:
http://github.com/samuelspiza/dvcsview

Options:

-f HOSTS, --fetch=HOSTS
  Pull/push-repos on these hosts will be checked if they are in sync. Argument
  is a comma separated list of the hosts. Hosts can be IPv4-addresses or
  domains. Windows volume letters (e.g. 'c:') and 1st level folder in the root
  directory (e.g. '/home') in Linux systems are possible too. Alias can be
  configured in '.dvcsview.conf'.

-q, --quiet
  Only one line per repository.

A template for the '.dvcsview.conf' can be found under:
http://gist.github.com/258034
"""

import sys, os, ConfigParser, optparse, re
from subprocess import call, Popen, PIPE

CONFIGFILES = [os.path.expanduser("~/.dvcsview.conf"), ".dvcsview.conf"]
WORKSPACES = "workspaces"
FETCH = "fetch"

def main(argv):
    config = ConfigParser.ConfigParser()
    config.read(CONFIGFILES)

    options = getOptions(argv)

    # replace fetch alias with configured hosts
    if config.has_section(FETCH):
        for opt in config.options(FETCH):
            if options.fetch == opt:
                options.fetch = config.get(FETCH, opt)

    # split comma separated list and strip elements
    options.fetch = [h.strip() for h in options.fetch.split(',')]
    
    repos = []
    workspaces = getWorkspaces(config)
    for workspace in workspaces:
        # creates 'Git' or 'Hg' objects and appends them to 'repos'
        findRepos(workspace, repos, options)
    for repo in repos:
        print repo.statusstring
    
    return 0

def getOptions(argv):
    parser = optparse.OptionParser()
    parser.add_option("-f", "--fetch",
                      dest="fetch", metavar="HOSTS", default="")
    parser.add_option("-q", "--quiet",
                      action="store_true", dest="quiet", default=False)
    return parser.parse_args(argv)[0]

def getWorkspaces(config):
    workspaces = [os.path.expanduser(w[1]) for w in config.items(WORKSPACES)]
    for w in workspaces[:]:
        if not os.path.exists(w):
            print "ERROR: Workspace '" + w + "' does not exist.\n"
            workspaces.remove(w)
    return workspaces

def findRepos(path, repos, options):
    entries = os.listdir(path)
    for entry in entries:
        if entry == ".git":
            repos.append(Git(path, options))
        elif entry == ".hg":
            repos.append(Hg(path, options))
        else:
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                findRepos(newpath, repos, options)

class WrappedFile:
    def __init__(self, path):
        self.file = open(path, "r")

    def readline(self):
        return self.file.readline().lstrip()

class Repo:
    def __init__(self, path, options):
        self.path = path
        os.chdir(self.path)
        self.options = options
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

    def buildStatusString(self):
        status = self.getStatus()
        if self.isClean(status):
            isClean = "CLEAN    "
        else:
            isClean = "NOT CLEAN"
        text = self.path
        if not self.options.quiet:
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

    def __init__(self, path, options):
        self.trackingbranches = None
        Repo.__init__(self, path, options)

    def getConfig(self):
        config = ConfigParser.ConfigParser()
        config.readfp(WrappedFile(self.configFile))
        return config

    def fetch(self):
        for remote in self.getRemotes():
            print "fetch %s" % self.path
            call("git fetch %s" % remote, shell=True)

    def getRemotes(self):
        remotesections = [s for s in self.config.sections()
                          if s.startswith("remote")]
        remotes = []
        for r in remotesections:
            m = self.re.search(self.config.get(r, "url"))
            if m.group(0) in self.options.fetch:
                remotes.append(r[8:-1])
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
    count = [("^?", "?"), ("^M", "M")]
    replace = []
    skip = []

    def fetch(self):
        paths = []
        if self.config is not None and self.config.has_option("paths", 'default'):
            paths.append(('default', "hg incoming"))
            if self.config.has_option("paths", 'default-push'):
                paths.append(('default-push', "hg outgoing"))
            else:
                paths.append(('default', "hg outgoing"))
        self.inout = []
        for p in paths:
            m = self.re.search(self.config.get("paths", p[0]))
            if m.group(0) in self.options.fetch:
                line = self.traffic(p[1])
                if line is not None:
                    self.inout.append(line)

    def traffic(self, cmd):
        s = len([l for l in self.pipe(cmd) if l.startswith("changeset")])
        if 0 < s:
            return "# %s: %s changesets" % (cmd[3:], s)
        else:
            return None

    def getStatus(self):
        return self.pipe("hg status")

    def isClean(self, status):
        return 0 == len(status)

    def getWarnings(self, status):
        return Repo.getWarnings(self, status) + self.inout

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
