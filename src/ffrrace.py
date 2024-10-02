import time
from datetime import timedelta
from sys import maxsize
import redis
import os

redis_db = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"),
                       port=int(os.environ.get("REDIS_PORT", "6379")))


class Race:
    """
    A class to model a FFR race
    """

    def __init__(self, id, name=None, lockable=False, flags=None):
        self.id = id
        self.name = name
        self.flags = flags
        self.runners = dict()
        self.started = False
        self.role = None
        self.channel = None
        self.owner = None
        self.readycount = 0
        self.message = None
        self.restream = None
        self.lockable = lockable
        self.islocked = False

    # def savedata(self):
    #     redis_db.hmset('active_races', json.dumps(active_races))
    #

    def addRunner(self, runnerid, runner):
        if not self.islocked:
            self.runners[runnerid] = dict(
                [("name", runner), ("stime", None), ("etime", None),
                 ("ready", False)])
        else:
            raise RaceLocked

    def removeRunner(self, runnerid):
        del self.runners[runnerid]

    def ready(self, runnerid):
        if (self.runners[runnerid]["ready"]):
            return
        self.runners[runnerid]["ready"] = True
        self.readycount += 1

    def unready(self, runnerid):
        if (self.runners[runnerid]["ready"] is False):
            return
        self.runners[runnerid]["ready"] = False
        self.readycount -= 1

    def start(self):
        self.started = True
        stime = time.perf_counter_ns()
        for runnerid in self.runners.values():
            runnerid["stime"] = stime

    def done(self, runnerid):
        etime = time.perf_counter_ns()
        runner = self.runners[runnerid]

        runner["etime"] = etime

        if (self.isFinished()):
            return self.getFinishedRaceMessage()

        rval = self._getTimeDeltaStr(etime, runner["stime"])
        return runner["name"] + ": " + rval

    def undone(self, runnerid):
        self.runners[runnerid]["etime"] = None
        return self.runners[runnerid]["name"] + " is back in the race!"

    def forfeit(self, runnerid):
        self.runners[runnerid]["etime"] = maxsize
        if (self.isFinished()):
            return self.getFinishedRaceMessage()

        return self.runners[runnerid]["name"] + " forfeited"

    def getUpdate(self):
        rval = "Current Entrants:\n"
        for runner in self.runners.values():
            rval += runner["name"] + " "
            if (self.started):
                if (runner["etime"] is maxsize):
                    rval += "forfeited"
                elif (runner["etime"] is not None):
                    time = self._getTimeDeltaStr(runner["etime"], runner["stime"])
                    rval += "done: " + time
                else:
                    rval += "still going"
            else:
                rval += ("ready" if runner["ready"] else "not ready")
            rval += "\n"
        return rval

    def getTime(self):       
        first = next(iter(self.runners.values()))
        return self._getTimeDeltaStr(time.perf_counter_ns(), first["stime"])

    def finishRace(self):
        rstring = "Race " + self.name + " results:\n\n"
        place = 0
        for runner in sorted(list(self.runners.values()),
                             key=lambda k: k["etime"]):
            place += 1
            rstring += str(place) + ") " + runner["name"] + ": "
            if (runner["etime"] is maxsize):
                rstring += "Forfeited\n"
            else:
                rstring += self._getTimeDeltaStr(runner["etime"], runner["stime"]) + "\n"
        return rstring

    def lockRace(self):
        if self.lockable is True:
            self.islocked = True
        else:
            raise RaceNotLockable

    def unlockRace(self):
        if self.islocked is True:
            self.islocked = False

    def isFinished(self):
        return all(r["etime"] is not None for r in self.runners.values())

    def _getTimeDeltaStr(self, end_time, start_time):
        return str(timedelta(microseconds=round(
            end_time - start_time, -3) // 1000))


class RaceLocked(Exception):
    """
    raised when attempting to add runners to a locked race
    """
    pass


class RaceNotLockable(Exception):
    """
    raised when attempting to lock a race that is not lockable
    """
    pass