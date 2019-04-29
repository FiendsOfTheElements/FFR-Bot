import time
from datetime import datetime, timedelta
from sys import maxsize

class Race:
    """
    A class to model a FFR race
    """

    def __init__(self, id, name = None, flags = None):
        self.id = id
        self.name = name
        self.flags = flags
        self.runners = dict()
        self.started = False
        self.role = None
        self.channel = None
        self.owner = None


    def addRunner(self, runnerid, runner):
        self.runners[runnerid] = dict([("name", runner), ("stime", None), ("etime", None), ("ready", False)])

    def removeRunner(self, runnerid):
        del self.runners[runnerid]

    def start(self):
        self.started = True
        stime = time.perf_counter_ns()
        for runnerid in self.runners.values():
            runnerid["stime"] = stime


    def done(self, runnerid):
        etime = time.perf_counter_ns()
        self.runners[runnerid]["etime"] = etime

        if (all(r["etime"] != None for r in self.runners.values())):
            return self.finishRace()

        rval = timedelta(microseconds=round(etime - self.runners[runnerid]["stime"], -3) // 1000)
        return self.runners[runnerid]["name"] + ": " + str(rval)

    def forfeit(self, runnerid):
        self.runners[runnerid]["etime"] = maxsize
        if (all(r["etime"] != None for r in self.runners.values())):
            return self.finishRace()

        return self.runners[runnerid]["name"] + " forfeited"

    def finishRace(self):
        rstring = "Race " + self.name + " results:\n\n"
        place = 0
        for runner in sorted(list(self.runners.values()), key=lambda k: k["etime"]):
            place += 1
            rstring += str(place) + ") " + runner["name"] + ": "
            if (runner["etime"] is maxsize):
                rstring += "Forfeited\n"
            else:
                rstring += str(timedelta(microseconds=round(runner["etime"] - runner["stime"], -3) // 1000)) + "\n"
        return rstring

