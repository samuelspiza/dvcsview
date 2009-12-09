#!/usr/bin/env python

import sys, os, re, ConfigParser
from subprocess import call, Popen, PIPE

CONFIGFILE = "~/.gitview.conf"
WORKSPACES = "gitview-workspaces"
COMMANDS = "gitview-commands"

def gitview():
    repos = []
    config = getConfig()
    for w in getworkspaces(config):
        findrepos(w, repos, config)
    for repo in repos:
        print repo.statusstring

def getConfig():
    conffile = os.path.expanduser(CONFIGFILE)
    config = ConfigParser.ConfigParser()
    succed = config.read([conffile])
    ok = getConfigCommands(config, succed)
    ok = getConfigWorkspaces(config, succed) and ok
    if not ok:
        with open(conffile, "w") as configfile:
            config.write(configfile)
        print "Please modify '" + conffile + "' according to your setup."
        sys.exit()
    return config

def getConfigCommands(config, succed):
    if 0 < len(succed) and config.has_section(COMMANDS):
        return True
    config.add_section(COMMANDS)
    if os.name == "nt":
        config.set(COMMANDS, "git", "C:\msysgit\git\git.exe")
    else:
        config.set(COMMANDS, "git", "git")
    return False

def getConfigWorkspaces(config, succed):
    if 0 < len(succed) and config.has_section(WORKSPACES):
        return True
    config.add_section(WORKSPACES)
    config.set(WORKSPACES, "workspace0", "~/workspace")
    return False

def getworkspaces(config):
    return [os.path.expanduser(w[1]) for w in config.items(WORKSPACES)]

def findrepos(path, repos, config):
    entries = os.listdir(path)
    if ".git" in entries:
        repos.append(Git(path, config))
    else:
        for entry in entries:
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                findrepos(newpath, repos, config)

class WrappedFile:
    def __init__(self, path):
        self.file = open(path, "r")

    def readline(self):
        return self.file.readline().lstrip()

class Git:
    def __init__(self, path, config):
        self.path = path
        os.chdir(self.path)
        self.config = config
        self.gitconfig = self.gitConfig()
        self.trackingbranches = self.getTrackingBranches()
        self.statusstring = self.buildStatusString()

    def gitConfig(self):
        gitconfig = ConfigParser.ConfigParser()
        gitconfig.readfp(WrappedFile(".git/config"))
        return gitconfig

    def getTrackingBranches(self):
        branches = [s for s in self.gitconfig.sections()
                      if s.startswith("branch")]
        return dict([(b[8:-1], None) for b in branches
                     if self.gitconfig.has_option(b, "merge")])

    def buildStatusString(self):
        status = self.gitStatus()
        if status[-1][:17] != "nothing to commit":
            return "NOT CLEAN " + self.path + self.gitWarnings(status)
        else:
            return "CLEAN " + self.path + self.gitWarningsAllBranches(status)

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
        return "".join(["\n  " + status[0] + ":" + s[1:] for s in status[1:]
                        if s.startswith("# ") and
                           not s[1:].startswith("  ")])

    def gitStatus(self):
        pipe = Popen(self.config.get(COMMANDS, "git") + " status", 
                     shell=True, stdout=PIPE).stdout
        status = [l.strip() for l in pipe.readlines()]
        self.trackingbranches[status[0][12:]] = status
        return status

    def gitCheckout(self, branch):
        retcode = call(self.config.get(COMMANDS, "git") + " checkout " + branch,
                       shell=True)

if __name__ == "__main__":
    gitview()
