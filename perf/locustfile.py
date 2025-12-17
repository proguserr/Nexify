from locust import HttpUser, task, between


class NexifyUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # TODO: if you add auth later, log in here
        pass

    @task(3)
    def list_tickets(self):
        self.client.get("/api/tickets/")

    @task(1)
    def ingest_ticket(self):
        payload = {
            "organization_id": 1,  # adjust once you know a real org id for perf env
            "requester_email": "perf@example.com",
            "subject": "perf test ticket",
            "body": "just load testing",
            "priority": "medium",
        }
        self.client.post("/api/tickets/ingest/", json=payload)
