#!/usr/bin/env python
import os, re, ConfigParser

def workspace():
    repos = []
    for w in getworkspaces():
        repos.extend(findrepos(w))
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

def findrepos(path):
    entries = os.listdir(path)
    if ".git" in entries:
        return [Git(path)]
    else:
        repos = []
        for entry in entries:
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                repos.extend(findrepos(newpath))
        return repos

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
        self.statusstring = self.buildStatusString()

    def getConfig(self):
        config = ConfigParser.ConfigParser()
        config.readfp(WrappedFile(".git/config"))
        return config

    def buildStatusString(self):
        status = [l.strip() for l in os.popen("git status").readlines()]
        if status[-1][:17] != "nothing to commit":
            statusstring = "NOT CLEAN " + self.path
        else:
            statusstring = "CLEAN " + self.path
        if 2 < len(status):
            warnings = ["  " + s for s in status[1:-2] if 0 < len(s[1:].strip())]
            statusstring = statusstring + "\n" + "\n".join(warnings[:3])
        return statusstring

    def __str__(self):
        return self.path


if __name__ == "__main__":
    workspace()
