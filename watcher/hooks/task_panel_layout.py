"""Calculate the compact task window and track height within an attachment."""


def visible_capacity(height):
    return min(4, max(0, height - 3))


def desired_height(plan):
    return 3 + visible_capacity(3 + len(plan["plan"] if plan else []))


class Height:
    def __init__(self):
        self.identity = None
        self.geometry = None
        self.target = None
        self.manual = False
        self.retry = False

    def attach(self, identity):
        if identity != self.identity:
            self.identity = identity
            self.geometry = None
            self.target = None
            self.manual = self.retry = False

    def choose(self, identity, manual):
        self.attach(identity)
        self.manual = manual
        self.target = None
        self.retry = False

    def fit(self, identity, geometry, target, resize):
        self.attach(identity)
        changed = geometry != self.geometry
        self.geometry = geometry
        if self.manual or (self.target == target and not self.retry and not changed):
            return
        if geometry[0] != target:
            self.retry = True
            self.geometry = resize(target - geometry[0])
        self.target, self.retry = target, False
