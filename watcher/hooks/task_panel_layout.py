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
        self.pending = None

    def fit(self, identity, geometry, target, resize):
        if identity != self.identity:
            self.identity = identity
            self.geometry = None
            self.target = None
            self.manual = self.retry = False
            self.pending = None
        if self.geometry is not None and geometry != self.geometry:
            if self.retry and geometry == self.pending:
                self.target, self.retry, self.pending = geometry[0], False, None
            else:
                self.manual, self.retry, self.pending = True, False, None
        self.geometry = geometry
        if self.manual or (self.target == target and not self.retry):
            return
        if geometry[0] != target:
            self.pending = (target, geometry[1])
            self.retry = True
            self.geometry = resize(target - geometry[0])
        self.target, self.retry, self.pending = target, False, None
