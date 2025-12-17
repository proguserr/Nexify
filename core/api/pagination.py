# core/api/pagination.py
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Default pagination for list endpoints.

    - Default page size: 20
    - Override with ?page_size=50
    - Hard cap at 100 to avoid abuse.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
