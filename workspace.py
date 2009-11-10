#!/usr/bin/env python
import os, re, ConfigParser

workspace = os.path.expanduser("~/workspace")

def find(path):
    entries = os.listdir(path)
    if ".git" in entries:
        foundgits.append(path)
    else:
        for entry in entries:
            newpath = os.path.join(path, entry)
            if os.path.isdir(newpath):
                find(newpath)

foundgits = []
servers = {}
def gitpush(gitdir):
    os.chdir(gitdir)
    print "  " + gitdir

    status = os.popen("git status").read()
    reg = r'nothing to commit'
    matchobj = re.search(reg, status)
    if matchobj is None:
        print "    has uncommited Changes ... exit"
        print
        return False

    config = ConfigParser.ConfigParser()
    file = open(".git/config", "r")
    lines = [l.strip() for l in file]
    file.close()
    file = open(".git/config.tm~", "w")
    file.write("\n".join(lines))
    file.close()
    config.read(".git/config.tm~")
    os.remove(".git/config.tm~")
    try:
        origin = config.get('remote "origin"', 'url', 0).split("@")[-1]
    except:
        print "    NO ORIGIN ... exit"
        print
        return False
    reg = r'([a-z0-9\.]*\.(com|net|org|de)|([0-9]{1,3}\.?){4})(?=(:|/))'
    server = re.search(reg,origin).group(0)
    print "    " + server

    if server not in servers:
        ping = os.popen("ping -c 3 " + server).read()
        reg = r'[0-9](?=\sreceived)'
        matchobj = re.search(reg,ping)
        if matchobj is None:
            received = 0
        else:
            received = matchobj.group(0)
        if 0 < int(received):
            servers[server] = True
        else:
            servers[server] = False

    if servers[server]:
        print "    AVAILABLE"
    else:
        print "    NOT AVAILABLE ... exit"
        print
        return False

    branches = [b[1:].strip() for b in os.popen("git branch").readlines() if 0 < len(b.strip())]
    for branch in branches:
        print "    git push origin " + branch

    print "    git push origin --tags"

    print

find(workspace)
for gitdir in foundgits:
    gitpush(gitdir)