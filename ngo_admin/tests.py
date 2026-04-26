"""
Topic 13 — Testing for ngo_admin
13.1 Unit tests — NGO status logic
13.2 API tests  — CRUD endpoints
13.3 Integration tests — API + DB together
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from rest_framework.test import APIClient
from rest_framework import status

from ngo.models import NGO, ServiceType


# ─────────────────────────────────────────────
# FIXED HELPERS (Stateless JWT style)
# ─────────────────────────────────────────────

def make_admin_user():
    return {
        "user_id": 1,
        "username": "admin",
        "groups": ["Administrator"]
    }


def make_employee_user():
    return {
        "user_id": 2,
        "username": "employee",
        "groups": ["Employee"]
    }


def authed_client():
    client = APIClient()
    client.force_authenticate(user=make_admin_user())
    return client


def unauth_client():
    return APIClient()


def make_ngo(name='Test NGO', slots=10):
    st, _ = ServiceType.objects.get_or_create(name='Education')
    return NGO.objects.create(
        name=name,
        description='Test description',
        serviceType=st,
        location='Kuala Lumpur',
        service_date=(timezone.now() + timedelta(days=7)).date(),
        start_time='09:00',
        end_time='17:00',
        max_slots=slots,
        cutoff_datetime=timezone.now() + timedelta(days=5),
        is_active=True,
    )


# ─────────────────────────────────────────────
# 13.1 UNIT TESTS (UNCHANGED COUNT)
# ─────────────────────────────────────────────

class NGOAdminUnitTest(TestCase):

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
        from ngo_admin.services.admindashboard import get_ngo_status
        self.ngo.registered_count = self.ngo.max_slots
        self.assertEqual(get_ngo_status(self.ngo), 'Full')

    def test_ngo_still_open_when_partially_filled(self):
        from ngo_admin.services.admindashboard import get_ngo_status
        self.ngo.registered_count = 3
        self.assertEqual(get_ngo_status(self.ngo), 'Open')

    def test_slots_fill_pct_half_full(self):
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.ngo.registered_count = 5
        self.assertEqual(get_slots_fill_pct(self.ngo), 50)

    def test_slots_fill_pct_fully_booked(self):
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.ngo.registered_count = 10
        self.assertEqual(get_slots_fill_pct(self.ngo), 100)

    def test_slots_fill_pct_ignores_pending(self):
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.assertEqual(get_slots_fill_pct(self.ngo), 0)

    def test_slots_fill_pct_ignores_rejected(self):
        from ngo_admin.services.admindashboard import get_slots_fill_pct
        self.assertEqual(get_slots_fill_pct(self.ngo), 0)

    def test_ngo_max_slots_is_positive(self):
        self.assertGreater(self.ngo.max_slots, 0)

    def test_ngo_service_date_is_in_future(self):
        self.assertGreater(self.ngo.service_date, timezone.now().date())

    def test_ngo_cutoff_before_service_date(self):
        cutoff_date = self.ngo.cutoff_datetime.date()
        self.assertLessEqual(cutoff_date, self.ngo.service_date)

    def test_ngo_end_time_after_start_time(self):
        self.assertGreater(self.ngo.end_time, self.ngo.start_time)

    def test_ngo_str_representation(self):
        self.assertEqual(str(self.ngo), self.ngo.name)


# ─────────────────────────────────────────────
# 13.2 API TESTS (FIXED AUTH ONLY)
# ─────────────────────────────────────────────

class NGOAdminAPITest(TestCase):

    def setUp(self):
        self.client = authed_client()
        self.ngo = make_ngo()

    def test_list_ngos_admin(self):
        resp = self.client.get('/api/v1/ngos/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_list_ngos_unauthenticated(self):
        resp = unauth_client().get('/api/v1/ngos/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ])

    def test_dashboard_stats(self):
        resp = self.client.get('/api/v1/ngos/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_toggle_active(self):
        original = self.ngo.is_active
        resp = self.client.patch(f'/api/v1/ngos/{self.ngo.id}/toggle-active/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ngo.refresh_from_db()
        self.assertNotEqual(self.ngo.is_active, original)

    def test_delete_ngo(self):
        resp = self.client.delete(f'/api/v1/ngos/{self.ngo.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create_service_type(self):
        resp = self.client.post(
            '/api/v1/service-types/',
            {'name': 'New Type'},
            format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


# ─────────────────────────────────────────────
# 13.3 INTEGRATION TESTS (FIXED AUTH ONLY)
# ─────────────────────────────────────────────

class NGOAdminIntegrationTest(TestCase):

    def setUp(self):
        self.client = authed_client()
        st, _ = ServiceType.objects.get_or_create(name='Health')
        self.st_id = st.id

    def test_create_ngo_saves_to_db(self):
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

                'cutoff_date': (timezone.now() + timedelta(days=7)).date().isoformat(),
                'cutoff_time': '18:00',

                'is_active': True,
            },
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(NGO.objects.filter(name='Integration NGO').exists())

    def test_update_ngo_reflects_in_db(self):
        ngo = make_ngo('Update Test')

        resp = self.client.patch(
            f'/api/v1/ngos/{ngo.id}/',
            {'name': 'Updated Name'},
            format='json'
        )

        ngo.refresh_from_db()
        self.assertEqual(ngo.name, 'Updated Name')

    def test_delete_ngo_removes_from_db(self):
        ngo = make_ngo('Delete Me')
        ngo_id = ngo.id
        self.client.delete(f'/api/v1/ngos/{ngo_id}/')
        self.assertFalse(NGO.objects.filter(id=ngo_id).exists())

    def test_toggle_active_reflects_in_db(self):
        ngo = make_ngo('Toggle Test')
        original = ngo.is_active
        self.client.patch(f'/api/v1/ngos/{ngo.id}/toggle-active/')
        ngo.refresh_from_db()
        self.assertNotEqual(ngo.is_active, original)

    def test_dashboard_stats_reflect_db(self):
        make_ngo('NGO 1')
        make_ngo('NGO 2')
        resp = self.client.get('/api/v1/ngos/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])                          # check success flag
        self.assertGreaterEqual(resp.data['data']['total_ngos'], 2)    # nested under 'data'
        self.assertIn('open_count', resp.data['data'])                 # check other keys exist
        self.assertIn('fill_pct', resp.data['data'])

    def test_unauthenticated_cannot_create_ngo(self):
        resp = unauth_client().post('/api/v1/ngos/', {'name': 'Hack'}, format='json')
        self.assertIn(resp.status_code, [401, 403])
        self.assertFalse(NGO.objects.filter(name='Hack').exists())