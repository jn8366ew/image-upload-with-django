import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_is_postgres():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
    assert connection.vendor == "postgresql"
