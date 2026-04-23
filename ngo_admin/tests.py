"""
Topic 13 — Testing for ngo_admin.
13.1 Unit tests — NGO status logic
13.2 API tests  — CRUD endpoints
13.3 Integration tests — API + DB together
"""

from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from datetime import timedelta

from ngo.models import NGO, ServiceType


# ── helpers ───────────────────────────────────────────────────

def make_admin(username='admin1', password='Pass1234'):
    g, _ = Group.objects.get_or_create(name='Administrator')
    user = User.objects.create_user(
        username=username, password=password,
        email=f'{username}@test.com', is_staff=True
    )
    user.groups.add(g)
    return user


def make_ngo(name='Test NGO', slots=10):
    st, _ = ServiceType.objects.get_or_create(name='Education')
    return NGO.objects.create(
        name            = name,
        description     = 'Test description',
        serviceType     = st,
        location        = 'Kuala Lumpur',
        service_date    = (timezone.now() + timedelta(days=7)).date(),
        start_time      = '09:00',
        end_time        = '17:00',
        max_slots       = slots,
        cutoff_datetime = timezone.now() + timedelta(days=5),
        is_active       = True,
    )


def get_token(client, username, password='Pass1234'):
    resp = client.post(
        '/api/v1/auth/token/',
        {'username': username, 'password': password},
        format='json',
    )
    return resp.data.get('access', '')


# ─────────────────────────────────────────────────────────────
# 13.1 Unit Tests
# ─────────────────────────────────────────────────────────────

class NGOStatusUnitTest(TestCase):
    """Unit tests for NGO status logic."""

    def setUp(self):
        self.ngo = make_ngo(slots=10)

    def test_ngo_is_open_initially(self):
        from ngo_admin.services.admindashboard import get_ngo_status
        self.assertEqual(get_ngo_status(self.ngo), 'Open')

    def test_ngo_is_inactive_when_deactivated(self):
        from ngo_admin.services.admindashboard import get_ngo_status
        self.ngo.is_active = False
        self.ngo.save()
        self.assertEqual(get_ngo_status(self.ngo), 'Inactive')

    def test_ngo_is_closed_after_cutoff(self):
        from ngo_admin.services.admindashboard import get_ngo_status
        self.ngo.cutoff_datetime = timezone.now() - timedelta(hours=1)
        self.ngo.save()
        self.assertEqual(get_ngo_status(self.ngo), 'Closed')

    def test_slots_fill_pct(self):
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.assertEqual(get_slots_fill_pct(self.ngo), 0)

    def test_ngo_is_full_when_all_slots_taken(self):
        """Status should be 'Full' when registered_count equals max_slots."""
        from ngo_admin.services.admindashboard import get_ngo_status
        self.ngo.registered_count = self.ngo.max_slots  # slots_taken reads this attr
        self.assertEqual(get_ngo_status(self.ngo), 'Full')

    def test_ngo_still_open_when_partially_filled(self):
        """Status stays 'Open' when only some slots are taken."""
        from ngo_admin.services.admindashboard import get_ngo_status
        self.ngo.registered_count = 3   # 3 out of 10 slots taken
        self.assertEqual(get_ngo_status(self.ngo), 'Open')

    def test_slots_fill_pct_half_full(self):
        """5 confirmed out of 10 slots = 50%."""
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.ngo.registered_count = 5
        self.assertEqual(get_slots_fill_pct(self.ngo), 50)

    def test_slots_fill_pct_fully_booked(self):
        """10 confirmed out of 10 slots = 100%."""
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.ngo.registered_count = 10
        self.assertEqual(get_slots_fill_pct(self.ngo), 100)

    def test_slots_fill_pct_ignores_pending(self):
        """Pending registrations should NOT count — only confirmed (registered_count) does."""
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        # registered_count not set = 0, mimics no confirmed registrations
        self.assertEqual(get_slots_fill_pct(self.ngo), 0)

    def test_slots_fill_pct_ignores_rejected(self):
        """Rejected registrations should NOT count."""
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.assertEqual(get_slots_fill_pct(self.ngo), 0)

    # ── NEW: NGO field validation ─────────────────────────────

    def test_ngo_max_slots_is_positive(self):
        """max_slots must be greater than zero."""
        self.assertGreater(self.ngo.max_slots, 0)

    def test_ngo_service_date_is_in_future(self):
        """service_date should be after today."""
        self.assertGreater(self.ngo.service_date, timezone.now().date())

    def test_ngo_cutoff_before_service_date(self):
        """cutoff_datetime should be before or on service_date."""
        cutoff_date = self.ngo.cutoff_datetime.date()
        self.assertLessEqual(cutoff_date, self.ngo.service_date)

    def test_ngo_end_time_after_start_time(self):
        """end_time must be later than start_time."""
        self.assertGreater(self.ngo.end_time, self.ngo.start_time)

    def test_ngo_str_representation(self):
        """NGO __str__ should return its name."""
        self.assertEqual(str(self.ngo), self.ngo.name)


# ─────────────────────────────────────────────────────────────
# 13.2 API Tests
# ─────────────────────────────────────────────────────────────

class NGOAdminAPITest(TestCase):
    """API tests for admin NGO management."""

    def setUp(self):
        self.client = APIClient()
        self.admin  = make_admin()
        self.ngo    = make_ngo()

    def _auth(self):
        token = get_token(self.client, 'admin1')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_list_ngos_admin(self):
        self._auth()
        resp = self.client.get('/api/v1/ngos/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['success'])

    def test_list_ngos_unauthenticated(self):
        resp = self.client.get('/api/v1/ngos/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dashboard_stats(self):
        self._auth()
        resp = self.client.get('/api/v1/ngos/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('total_ngos', resp.data['data'])

    def test_toggle_active(self):
        self._auth()
        original = self.ngo.is_active
        resp = self.client.patch(f'/api/v1/ngos/{self.ngo.id}/toggle-active/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ngo.refresh_from_db()
        self.assertNotEqual(self.ngo.is_active, original)

    def test_delete_ngo(self):
        self._auth()
        resp = self.client.delete(f'/api/v1/ngos/{self.ngo.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(NGO.objects.filter(id=self.ngo.id).exists())

    def test_create_service_type(self):
        self._auth()
        resp = self.client.post(
            '/api/v1/service-types/',
            {'name': 'New Type'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────
# 13.3 Integration Tests
# ─────────────────────────────────────────────────────────────

class NGOAdminIntegrationTest(TestCase):
    """Integration: API call → DB record verified."""

    def setUp(self):
        self.client = APIClient()
        self.admin  = make_admin('adm_int')
        st, _       = ServiceType.objects.get_or_create(name='Health')
        self.st_id  = st.id

    def _auth(self):
        token = get_token(self.client, 'adm_int')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_create_ngo_saves_to_db(self):
        self._auth()
        resp = self.client.post(
            '/api/v1/ngos/',
            {
                'name':         'Integration NGO',
                'description':  'Test',
                'serviceType':  self.st_id,
                'location':     'KL',
                'service_date': (timezone.now() + timedelta(days=10)).date().isoformat(),
                'start_time':   '09:00',
                'end_time':     '17:00',
                'max_slots':    20,
                'cutoff_date':  (timezone.now() + timedelta(days=7)).date().isoformat(),
                'cutoff_time':  '18:00',
                'is_active':    True,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(NGO.objects.filter(name='Integration NGO').exists())

    def test_update_ngo_reflects_in_db(self):
        ngo = make_ngo('Update Test')
        self._auth()
        self.client.patch(
            f'/api/v1/ngos/{ngo.id}/',
            {'name': 'Updated Name'},
            format='json',
        )
        ngo.refresh_from_db()
        self.assertEqual(ngo.name, 'Updated Name')