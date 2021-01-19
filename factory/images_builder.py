#!/usr/bin/env python
# -*- coding: utf-8 -*-
from buildbot.plugins import *
from twisted.internet import defer
from buildbot.plugins import reporters, util
from buildbot.process.properties import Interpolate
from buildbot.steps.shell import ShellCommand
from buildbot.status.builder import SUCCESS, SKIPPED, FAILURE, WARNINGS
from buildbot.process.buildstep import LogLineObserver
import re
import pprint
import os

@util.renderer
def BuildStatus(step):
    if step.build.results == FAILURE:
        return "failed"
    if step.build.results == SUCCESS:
        return "passed"
    return "failed-other"

@util.renderer
def PatchStatus(props):
    print(props.getBuild())
    step = props.getBuild().executedSteps[-1]
    print("step.build")
    print(step.build.buildid)
    print("step.executedsteps")
    for i in step.build.executedSteps:
        print(i.name)
        if i.name == "Patching kernel":
            print("results of i")
            if i.results == FAILURE:
                print("results is failure")
    print("step.stepnames")
    print(step.build.stepnames)
    print("step.currentstep")
    print(step.build.currentStep)
    print(str(step.build))

@util.renderer
@defer.inlineCallbacks
def stepLogsID(props):
    step = props.getBuild().executedSteps[-1]
    logs = yield step.master.data.get(('steps', step.stepid, 'logs'))
    print(logs)
    for l in logs:
        print(l['logid'])

def download_new_patch_and_build_kernel(version, arch):
    factory = util.BuildFactory()
#    factory.addStep(steps.ShellCommand(description="Cleaning enviroment",
#                                 descriptionDone='Cleaned enviroment',
#                                 name='Clean enviroment',
#                                 command=["/bin/bash", "-c", "umask 022; rm -rf *"],
#                                 alwaysRun=True,
#                                 logEnviron=False,
#                                 timeout=2400))
#
#    factory.addStep(steps.GitHub(name="Fetching linux-patches",
#                                 repourl='https://github.com/gentoo/linux-patches',
#                                 mode='incremental',
#                                 logEnviron=False,
#                                 workdir="build/linux-patches", branch=version))
#    
#    factory.addStep(steps.GitHub(name="Fetching Ghelper",
#                                 repourl='https://github.com/GKernelCI/Ghelper.git',
#                                 mode='incremental',
#                                 alwaysRun=True,
#                                 alwaysUseLatest=True,
#                                 logEnviron=False,
#                                 workdir="build/ghelper", branch='master'))

    factory.addStep(steps.ShellCommand(name="Looking for new upstream release",
                                       command=["/usr/bin/python3",
                                                "check-kernelpage.py",
                                                "--version", version],
                                       workdir="build/ghelper/",
                                       logEnviron=False,
                                       alwaysRun=True,
                                       haltOnFailure=True))

    factory.addStep(steps.ShellCommand(name="Patching kernel",
                                       command=["/bin/bash", "patch-kernel.sh",
                                                "-a", arch, "-k", version, stepLogsID],
                                       workdir="build/ghelper/",
                                       alwaysRun=True,
                                       logEnviron=False,
                                       haltOnFailure=True))

    factory.addStep(steps.ShellCommand(name="Listing rejected files",
                                       command=["/bin/bash", "find.sh"],
                                       logEnviron=False,
                                       workdir="build/ghelper/"))

    factory.addStep(steps.ShellCommand(name="Building kernel",
                                       command=["/bin/bash", "../build-kernel.sh", arch],
                                       workdir="build/ghelper/linux-" + version + "/",
                                       logEnviron=False,
                                       haltOnFailure=True))

    factory.addStep(steps.ShellCommand(name="Building modules",
                                       command=["/bin/bash", "../build-kernel.sh", arch, "modules"],
                                       workdir="build/ghelper/linux-" + version + "/",
                                       logEnviron=False,
                                       haltOnFailure=True))

    factory.addStep(steps.ShellCommand(name="Move kernel to fileserver",
                                       command=["/bin/bash", "to_fileserver.sh", arch,
                                                util.Property('buildername'), util.Property('buildnumber')],
                                       logEnviron=False,
                                       workdir="build/ghelper/", timeout=3600))
    
    factory.addStep(steps.ShellCommand(name="Run Gentoo kernel tests",
                                       command=["/bin/bash", "run_tests.sh", arch,
                                                util.Property('buildername'), util.Property('buildnumber')],
                                       logEnviron=False,
                                       workdir="build/ghelper/", timeout=3600))
    factory.addStep(steps.ShellCommand(name="Send report to KCIDB",
                                       command=["/bin/bash", "kcidb/sendtokcidb", version,
                                                util.Property('buildername'), util.Property('buildnumber'),
                                                BuildStatus, arch, PatchStatus],
                                       logEnviron=False,
                                       alwaysRun=True,
                                       workdir="build/ghelper/", timeout=3600))
    return factory


@util.renderer
def filterFiles(props):
    files = props.getBuild().allFiles()
    print(files)
    build_files = [s for s in files if "sys-kernel/" in s]
    command = ["/usr/bin/python3", "stabilize-packages.py"]
    for file in build_files:
        command.append(file)
    print(str(command))
    return command

@util.renderer
def pull_repourl(props):
    pull_repourl = props.getProperty('repository')
    return pull_repourl

def test_gentoo_sources():
    factory = util.BuildFactory()
    factory.addStep(steps.ShellCommand(description="Cleaning enviroment",
                                 descriptionDone='Cleaned enviroment',
                                 name='Clean enviroment',
                                 command=["/bin/bash", "-c", "umask 022; rm -rf *"],
                                 logEnviron=False,
                                 timeout=2400))
    factory.addStep(steps.GitHub(name="Fetching repository",
                                 repourl=pull_repourl,
                                 logEnviron=False,
                                 mode='incremental', workdir="build/gentoo", shallow=50))
    factory.addStep(steps.GitHub(name="Fetching Ghelper",
                                 repourl='https://github.com/GKernelCI/Ghelper.git',
                                 mode='incremental',
                                 logEnviron=False,
                                 alwaysUseLatest=True,
                                 workdir="build/ghelper", branch='master'))
    factory.addStep(steps.ShellCommand(name="Stabilizing package",
                                       command=filterFiles,
                                       logEnviron=False,
                                       workdir="build/ghelper/"))
    return factory

