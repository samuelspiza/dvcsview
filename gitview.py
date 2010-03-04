#!/usr/bin/env python

'''
Gitview is hosted on Github. Checkout:
http://github.com/samuelspiza/gitview

A template for the '~/.gitview.conf' can be found under:
http://gist.github.com/258034
'''

import sys, os, ConfigParser, optparse, re
from subprocess import call, Popen, PIPE

CONFIGFILES = [os.path.expanduser("~/.gitview.conf"), ".gitview.conf"]
WORKSPACES = "gitview-workspaces"

def main(argv):
    repos = []
    config = getConfig()
    options = getOptions(argv)
    for w in getworkspaces(config):
        findrepos(w, repos, options)
    for repo in repos:
        print repo.statusstring

def getConfig():
    config = ConfigParser.ConfigParser()
    config.read(CONFIGFILES)
    return config

def getOptions(argv):
    parser = optparse.OptionParser()
    parser.add_option("-f", "--fetch", dest="fetch", metavar="URLS",
                      default="/home,e:")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet",
                      default=False)
    return parser.parse_args(argv)[0]

def getworkspaces(config):
    workspaces = [os.path.expanduser(w[1]) for w in config.items(WORKSPACES)]
    for w in workspaces[:]:
        if not os.path.exists(w):
            print "ERROR: Workspace '" + w + "' does not exist.\n"
            workspaces.remove(w)
    return workspaces

def findrepos(path, repos, options):
    entries = os.listdir(path)
    if ".git" in entries:
        repos.append(Git(path, options))
    elif ".hg" in entries:
        repos.append(Hg(path, options))
    for entry in entries:
        if entry != ".git" and entry != ".hg":
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                findrepos(newpath, repos, options)

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
        url = "(?<=/|@)[a-z0-9-]*\.(?:com|de|net|org)(?=[:/])"
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

class Git(Repo):
    typ = "Git"
    configFile = ".git/config"
    
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
            if m.group(0) in self.options.fetch.split(","):
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
                status = self.gitStatus()
        if status[0][12:] != defaultbranch:
            call("git checkout %s" % defaultbranch, shell=True)

    def getWarnings(self, status):
        warnings = []
        for b in self.trackingbranches.items():
            status = b[1]
            if status is not None:
                warnings.extend([status[0] + ":" + s[1:] for s in status[1:]
                                 if s.startswith("# ") and
                                    not s[1:].startswith("  ")])
        return warnings

class Hg(Repo):
    typ = "Hg "
    configFile = ".hg/hgrc"
    
    def __init__(self, path, options):
        Repo.__init__(self, path, options)
    
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
            if m.group(0) in self.options.fetch.split(","):
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
        return status + self.inout

if __name__ == "__main__":
    main(sys.argv[1:])
