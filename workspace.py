#!/usr/bin/env python
import os, re, ConfigParser

workspaces = [os.path.expanduser("~/workspace/python"),
              os.path.expanduser("~/workspace/web")]

def workspace():
    repos = []
    for w in workspaces:
        repos.extend(findrepos(w))
    for repo in repos:
        print repo

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
        status = os.popen("git status").read()
        reg = r'nothing to commit'
        matchobj = re.search(reg, status)
        if matchobj is None:
            return "NOT CLEAR " + self.path
        else:
            return "CLEAR " + self.path

    def __str__(self):
        return self.statusstring


if __name__ == "__main__":
    workspace()
