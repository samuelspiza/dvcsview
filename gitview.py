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
        findrepos(w, repos, config, options)
    for repo in repos:
        print repo.statusstring

def getConfig():
    config = ConfigParser.ConfigParser()
    config.read(CONFIGFILES)
    return config

def getOptions(argv):
    parser = optparse.OptionParser()
    parser.add_option("-f", "--fetch", dest="fetch", metavar="URLS",
                      default="/home,e")
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

def findrepos(path, repos, config, options):
    entries = os.listdir(path)
    if ".git" in entries:
        repos.append(Git(path, config, options))
    elif ".hg" in entries:
        repos.append(Hg(path, config, options))
    for entry in entries:
        if entry != ".git" and entry != ".hg":
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                findrepos(newpath, repos, config, options)

class WrappedFile:
    def __init__(self, path):
        self.file = open(path, "r")

    def readline(self):
        return self.file.readline().lstrip()

class Repo:
    def __init__(self, path, config, options):
        self.path = path
        os.chdir(self.path)
        self.config = config
        self.options = options

class Git(Repo):
    def __init__(self, path, config, options):
        Repo.__init__(self, path, config, options)
        self.gitconfig = self.gitConfig()
        self.fetch()
        self.trackingbranches = self.getTrackingBranches()
        self.statusstring = self.buildStatusString()

    def gitConfig(self):
        gitconfig = ConfigParser.ConfigParser()
        gitconfig.readfp(WrappedFile(".git/config"))
        return gitconfig

    def fetch(self):
        for remote in self.getRemotes():
            self.gitFetch(remote)

    def getRemotes(self):
        remotesections = [s for s in self.gitconfig.sections()
                          if s.startswith("remote")]
        remotes = []
        for r in remotesections:
            ipseg = "[12]?[0-9]{1,2}"
            ip = "(?<=@)(?:" + ipseg + "\.){3}" + ipseg + "(?=[:/])"
            url = "(?<=/|@)[a-z0-9-]*\.(?:com|de|net|org)(?=[:/])"
            d = "^(?:/[a-z]+(?=/)|[a-z]:)"
            regexp = "|".join([ip, url, d])
            m = re.search(regexp, self.gitconfig.get(r, "url"))
            if m.group(0) in self.options.fetch.split(","):
                remotes.append(r[8:-1])
        return remotes

    def getTrackingBranches(self):
        branches = [s for s in self.gitconfig.sections()
                      if s.startswith("branch")]
        return dict([(b[8:-1], None) for b in branches
                     if self.gitconfig.has_option(b, "merge")])

    def buildStatusString(self):
        status = self.gitStatus()
        if status[-1][:17] != "nothing to commit":
            return "NOT CLEAN Git " + self.path + self.gitWarnings(status)
        else:
            return "CLEAN     Git " + self.path + self.gitWarningsAllBranches(status)

    def gitWarningsAllBranches(self, status):
        defaultbranch = status[0][12:]
        for b in self.trackingbranches.items():
            if b[0] != status[0][12:]:
                self.gitCheckout(b[0])
                status = self.gitStatus()
        if status[0][12:] != defaultbranch:
            self.gitCheckout(defaultbranch)
        statuslist = self.trackingbranches.values()
        return "".join([self.gitWarnings(s) for s in statuslist])

    def gitWarnings(self, status):
        if self.options.quiet:
            return ""
        return "".join(["\n  " + status[0] + ":" + s[1:] for s in status[1:]
                        if s.startswith("# ") and
                           not s[1:].startswith("  ")])

    def gitStatus(self):
        pipe = Popen("git status", shell=True, stdout=PIPE).stdout
        status = [l.strip() for l in pipe.readlines()]
        self.trackingbranches[status[0][12:]] = status
        return status

    def gitCheckout(self, branch):
        call("git checkout %s" % branch, shell=True)

    def gitFetch(self, remote):
        print "fetch %s" % self.path
        call("git fetch %s" % remote, shell=True)

class Hg(Repo):
    def __init__(self, path, config, options):
        Repo.__init__(self, path, config, options)
        self.statusstring = self.buildStatusString()
    
    def buildStatusString(self):
        status = self.hgStatus()
        print status
        if 0 < len(status):
            return "NOT CLEAN Hg  %s%s" % (self.path, self.hgWarnings(status))
        else:
            return "CLEAN     Hg  %s" % self.path

    def hgStatus(self):
        pipe = Popen("hg status", shell=True, stdout=PIPE).stdout
        return [l.strip() for l in pipe.readlines()]

    def hgWarnings(self, status):
        if self.options.quiet:
            return ""
        return "".join(["\n  " + s for s in status])

if __name__ == "__main__":
    main(sys.argv[1:])
