#!/usr/bin/env python
import os, re, ConfigParser

workspaces = [os.path.expanduser("~/workspace/python"),
              os.path.expanduser("~/workspace/web")]

def workspace():
    repos = []
    for w in workspaces:
        repos.extend(findrepos(w))
    for repo in repos:
        print repo.statusstring

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

class Git():
    def __init__(self, path):
        self.path = path
        os.chdir(self.path)
        self.config = self.getConfig()
        self.statusstring = self.buildStatusString()

    def getConfig(self):
        config = ConfigParser.ConfigParser()
        file = open(".git/config", "r")
        lines = [l.strip() for l in file]
        file.close()
        file = open(".git/config.tm~", "w")
        file.write("\n".join(lines))
        file.close()
        config.read(".git/config.tm~")
        os.remove(".git/config.tm~")
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
