"""Mock GitHub Projects v2 GraphQL adapter. No network. Same method surface the real App adapter will expose."""
import itertools, datetime as dt

class GitHubAdapter:
    """Interface. A real adapter (GitHub App installation token) is out of scope until Scotty installs the App."""
    def get_project_item(self, project_id, item_id): raise NotImplementedError
    def add_item(self, project_id, content_node_id): raise NotImplementedError
    def update_field(self, project_id, item_id, field, value): raise NotImplementedError

class MockGraphQLAdapter(GitHubAdapter):
    PROJECT_ID = "PVT_mock_project"

    def __init__(self):
        self.items = {}           # project_item_id -> {"content": node_id, "fields": {}, "updatedAt": str}
        self.by_content = {}
        self.calls = []           # (mutation/query name, args) for assertions
        self._seq = itertools.count(1)
        self._clock = itertools.count(1)
        self.fail_on = set()      # node ids that raise, to test error paths

    def _ts(self):
        return (dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=next(self._clock))).isoformat()

    # --- GraphQL-shaped operations -------------------------------------------------
    def add_item(self, project_id, content_node_id):
        self.calls.append(("addProjectV2ItemById", content_node_id))
        if content_node_id in self.fail_on: raise RuntimeError("mock: addProjectV2ItemById failed")
        if content_node_id in self.by_content:            # GitHub is idempotent here too
            return self.by_content[content_node_id]
        pid = f"PVTI_mock{next(self._seq):04d}"
        self.items[pid] = {"content": content_node_id, "fields": {}, "updatedAt": self._ts()}
        self.by_content[content_node_id] = pid
        return pid

    def update_field(self, project_id, item_id, field, value):
        self.calls.append(("updateProjectV2ItemFieldValue", item_id, field, value))
        it = self.items[item_id]
        it["fields"][field] = value
        it["updatedAt"] = self._ts()
        return it["updatedAt"]

    def get_project_item(self, project_id, item_id):
        self.calls.append(("node(ProjectV2Item)", item_id))
        it = self.items.get(item_id)
        return None if it is None else {"id": item_id, "fields": dict(it["fields"]), "updatedAt": it["updatedAt"]}

    # --- test helper: simulate a human editing the Project in GitHub ---------------
    def remote_edit(self, item_id, field, value):
        self.items[item_id]["fields"][field] = value
        self.items[item_id]["updatedAt"] = self._ts()
