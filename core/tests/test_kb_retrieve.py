import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Organization, Membership, Document, DocumentChunk


@pytest.mark.django_db
def test_kb_retrieve_returns_expected_shape():
    client = APIClient()

    org = Organization.objects.create(name="Org 1")
    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org, role="agent")

    # Minimal doc + chunk
    doc = Document.objects.create(
        organization=org,
        title="Refund Policy",
        text="Refunds allowed within 14 days.",
        metadata={},
        uploaded_by=user,
    )
    DocumentChunk.objects.create(
        organization=org,
        document=doc,
        chunk_index=0,
        text="Refunds allowed within 14 days.",
    )

    client.force_authenticate(user=user)

    resp = client.post(
        f"/api/organizations/{org.id}/kb/retrieve/",
        {"query": "refund", "k": 3},
        format="json",
    )

    assert resp.status_code == 200
    assert "results" in resp.data

    for row in resp.data["results"]:
        assert set(row.keys()) == {
            "document_id",
            "document_title",
            "chunk_id",
            "chunk_index",
            "text",
            "score",
        }
