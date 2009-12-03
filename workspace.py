#!/usr/bin/env python
import os, re, ConfigParser
from subprocess import call, Popen, PIPE, STDOUT

def workspace():
    repos = []
    for w in getworkspaces():
        findrepos(w, repos)
    for repo in repos:
        print repo.statusstring

def getworkspaces():
    config = ConfigParser.ConfigParser()
    succed = config.read([os.path.expanduser("~/.backupscripts.conf")])
    if 0 == len(succed) or not config.has_section("workspace"):
        config.add_section("workspace")
        config.set("workspace", "randomname", "~/workspace")
        with open(os.path.expanduser("~/.backupscripts.conf"), "w") as configfile:
            config.write(configfile)
    return [os.path.expanduser(w[1]) for w in config.items("workspace")]

def findrepos(path, repos):
    entries = os.listdir(path)
    if ".git" in entries:
        repos.append(Git(path))
    else:
        for entry in entries:
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                findrepos(newpath, repos)

class WrappedFile:
    def __init__(self, path):
        self.file = open(path, "r")

    def readline(self):
        return self.file.readline().lstrip()

class Git:
    def __init__(self, path):
        self.path = path
        os.chdir(self.path)
        self.config = self.getConfig()
        self.trackingbranches = self.getTrackingBranches()
        self.statusstring = self.buildStatusString()

    def getConfig(self):
        config = ConfigParser.ConfigParser()
        config.readfp(WrappedFile(".git/config"))
        return config

    def getTrackingBranches(self):
        branches = [s for s in self.config.sections() if s.startswith("branch")]
        return [b[8:-1] for b in branches if self.config.has_option(b, "merge")]

    def buildStatusString(self):
        status = self.gitStatus()
        if status[-1][:17] != "nothing to commit":
            return "NOT CLEAN " + self.path + "\n  " + status[1]
        else:
            statusstring = "CLEAN " + self.path
        defaultbranch = status[0][12:]
        for b in self.trackingbranches:
            if b != status[0][12:]:
                self.gitCheckout(b)
            status = self.gitStatus()
            if 2 < len(status):
                statusstring = statusstring + "\n  " + status[0] + ": " + status[1][2:]
        if status[0][12:] != defaultbranch:
            self.gitCheckout(defaultbranch)
        return statusstring

    def gitStatus(self):
        pipe = Popen("git status", shell=True, stdout=PIPE).stdout
        return [l.strip() for l in pipe.readlines()]

    def gitCheckout(self, branch):
        retcode = call("git" + " checkout " + branch, shell=True)

    def __str__(self):
        return self.path


if __name__ == "__main__":
    workspace()
