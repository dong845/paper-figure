class PaperFigError(Exception):
    """Base error. Messages are meant to be shown to the user verbatim."""


class BlueprintError(PaperFigError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("blueprint has %d problem(s):\n- " % len(self.problems) + "\n- ".join(self.problems))


class LayoutError(PaperFigError):
    pass


class RouteError(PaperFigError):
    def __init__(self, edge_id, detail=""):
        self.edge_id = edge_id
        super().__init__(f"no orthogonal route found for edge '{edge_id}'" + (f": {detail}" if detail else ""))


class ExportError(PaperFigError):
    pass


class StyleError(PaperFigError):
    pass
