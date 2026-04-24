from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, date, time
from rest_framework.test import APIClient
from rest_framework import status
from ngo.models import NGO, ServiceType, Organizer
from ngo_employee.serializers import NGOEmployeeListSerializer, NGOEmployeeDetailSerializer
import jwt
import datetime
from django.conf import settings


# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

def make_service_type(name='Environment'):
    return ServiceType.objects.create(name=name)


def make_organizer(name='Green Org'):
    return Organizer.objects.create(
        company_name=name,
        description='A test organizer'
    )


def make_ngo(
    name='River Cleanup',
    max_slots=10,
    days_ahead=30,
    cutoff_days_ahead=10,
    is_active=True,
    service_type=None,
    organizer=None,
):
    """Helper to create a test NGO with sensible defaults."""
    st  = service_type or make_service_type()
    org = organizer    or make_organizer()
    return NGO.objects.create(
        name            = name,
        description     = 'Help clean the river',
        serviceType     = st,
        organizer       = org,
        location        = 'Kuala Lumpur',
        service_date    = date.today() + timedelta(days=days_ahead),
        start_time      = time(9, 0),
        end_time        = time(17, 0),
        max_slots       = max_slots,
        cutoff_datetime = timezone.now() + timedelta(days=cutoff_days_ahead),
        is_active       = is_active,
    )


def employee_token(user_id=5, username='employee1'):
    """Generate a valid employee JWT token."""
    return jwt.encode({
        'user_id':  user_id,
        'username': username,
        'groups':   ['Employee'],
        'exp':      datetime.datetime(2099, 1, 1)
    }, settings.SECRET_KEY, algorithm='HS256')


def admin_token():
    """Generate a valid admin JWT token."""
    return jwt.encode({
        'user_id':  0,
        'username': 'admin',
        'groups':   ['Administrator'],
        'exp':      datetime.datetime(2099, 1, 1)
    }, settings.SECRET_KEY, algorithm='HS256')


# ─────────────────────────────────────────────
# 1. NGO Model Tests (employee perspective)
# ─────────────────────────────────────────────

class NGOEmployeeModelTest(TestCase):
    """
    Topic 13.1 — Unit tests for NGO model properties
    that employees rely on (status, availability, cutoff).
    """

    def test_ngo_is_active_by_default(self):
        """Active NGO is visible to employees."""
        ngo = make_ngo()
        self.assertTrue(ngo.is_active)

    def test_ngo_is_not_closed_before_cutoff(self):
        """NGO is open when cutoff has not passed."""
        ngo = make_ngo(cutoff_days_ahead=5)
        self.assertFalse(ngo.is_closed)

    def test_ngo_is_closed_after_cutoff(self):
        """NGO is closed when cutoff has passed."""
        st  = make_service_type('Health')
        org = make_organizer('Health Org')
        ngo = NGO.objects.create(
            name            = 'Closed NGO',
            description     = 'desc',
            serviceType     = st,
            organizer       = org,
            location        = 'KL',
            service_date    = date.today() + timedelta(days=5),
            start_time      = time(9, 0),
            end_time        = time(17, 0),
            max_slots       = 10,
            cutoff_datetime = timezone.now() - timedelta(hours=1),  # ← past
            is_active       = True,
        )
        self.assertTrue(ngo.is_closed)

    def test_ngo_available_slots_full(self):
        """available_slots returns 0 when no registrations exist (via model property)."""
        ngo = make_ngo(max_slots=10)
        # no registered_count injected → slots_taken = 0
        self.assertEqual(ngo.available_slots, 10)

    def test_ngo_is_not_full_when_slots_available(self):
        """is_full returns False when slots > 0."""
        ngo = make_ngo(max_slots=5)
        self.assertFalse(ngo.is_full)

    def test_ngo_is_ended_false_for_future_event(self):
        """is_ended is False for an event happening in the future."""
        ngo = make_ngo(days_ahead=30)
        self.assertFalse(ngo.is_ended)

    def test_ngo_is_ended_true_for_past_event(self):
        """is_ended is True for an event that has already ended."""
        st  = make_service_type('Community')
        org = make_organizer('Community Org')
        ngo = NGO.objects.create(
            name            = 'Past Event',
            description     = 'desc',
            serviceType     = st,
            organizer       = org,
            location        = 'KL',
            service_date    = date.today() - timedelta(days=5),
            start_time      = time(0, 0),
            end_time        = time(1, 0),
            max_slots       = 10,
            cutoff_datetime = timezone.now() - timedelta(days=10),
            is_active       = True,
        )
        self.assertTrue(ngo.is_ended)

    def test_slots_taken_percent_zero_when_empty(self):
        """slots_taken_percent is 0 when no registrations."""
        ngo = make_ngo(max_slots=20)
        self.assertEqual(ngo.slots_taken_percent, 0)

    def test_slots_taken_percent_zero_when_max_slots_zero(self):
        """slots_taken_percent handles max_slots=0 gracefully."""
        ngo = make_ngo(max_slots=1)
        ngo.max_slots = 0  # simulate edge case
        self.assertEqual(ngo.slots_taken_percent, 0)

    def test_ngo_str_representation(self):
        """NGO string representation returns name."""
        ngo = make_ngo(name='Beach Cleanup')
        self.assertEqual(str(ngo), 'Beach Cleanup')

    def test_inactive_ngo_exists_in_db(self):
        """Inactive NGO is saved to DB but should be hidden from employees."""
        ngo = make_ngo(is_active=False)
        self.assertFalse(ngo.is_active)
        self.assertTrue(NGO.objects.filter(id=ngo.id).exists())


# ─────────────────────────────────────────────
# 2. Employee Serializer Tests
# ─────────────────────────────────────────────

class NGOEmployeeSerializerTest(TestCase):
    """
    Topic 13.1 — Unit tests for NGOEmployeeListSerializer
    and NGOEmployeeDetailSerializer.
    """

    def setUp(self):
        self.st  = make_service_type('Education')
        self.org = make_organizer('Edu Org')
        self.ngo = make_ngo(
            name         = 'Tuition Drive',
            max_slots    = 20,
            service_type = self.st,
            organizer    = self.org,
        )

    def test_serializer_contains_expected_fields(self):
        """Serializer returns all required fields."""
        s    = NGOEmployeeListSerializer(self.ngo, context={'registration_counts': {}})
        data = s.data
        for field in [
            'id', 'name', 'description', 'serviceType',
            'location', 'service_date', 'start_time', 'end_time',
            'max_slots', 'slots_taken', 'available_slots',
            'slots_taken_percent', 'status', 'is_active',
            'is_full', 'is_closed',
        ]:
            self.assertIn(field, data, f"Missing field: {field}")

    def test_status_open_when_slots_available(self):
        """Status is 'open' when slots available and not closed."""
        s    = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 0}}
        )
        self.assertEqual(s.data['status'], 'open')

    def test_status_full_when_all_slots_taken(self):
        """Status is 'full' when all slots taken."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 20}}  # all 20 taken
        )
        self.assertEqual(s.data['status'], 'full')

    def test_status_almost_full_when_50_percent_taken(self):
        """Status is 'almost_full' when >= 50% slots taken."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 11}}  # 11/20 = 55%
        )
        self.assertEqual(s.data['status'], 'almost_full')

    def test_status_closed_after_cutoff(self):
        """Status is 'closed' when cutoff has passed."""
        st  = make_service_type('Animal')
        org = make_organizer('Animal Org')
        closed_ngo = NGO.objects.create(
            name            = 'Closed Activity',
            description     = 'desc',
            serviceType     = st,
            organizer       = org,
            location        = 'KL',
            service_date    = date.today() + timedelta(days=5),
            start_time      = time(9, 0),
            end_time        = time(17, 0),
            max_slots       = 10,
            cutoff_datetime = timezone.now() - timedelta(hours=1),
            is_active       = True,
        )
        s = NGOEmployeeListSerializer(
            closed_ngo,
            context={'registration_counts': {str(closed_ngo.id): 0}}
        )
        self.assertEqual(s.data['status'], 'closed')

    def test_slots_taken_from_context(self):
        """slots_taken reads from registration_counts context."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 7}}
        )
        self.assertEqual(s.data['slots_taken'], 7)

    def test_available_slots_calculation(self):
        """available_slots = max_slots - slots_taken."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 5}}
        )
        self.assertEqual(s.data['available_slots'], 15)  # 20 - 5

    def test_available_slots_never_negative(self):
        """available_slots never goes below 0 even if overbooked."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 999}}  # way over max
        )
        self.assertGreaterEqual(s.data['available_slots'], 0)

    def test_slots_taken_percent_calculation(self):
        """slots_taken_percent = (taken / max) * 100 rounded."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 10}}  # 10/20 = 50%
        )
        self.assertEqual(s.data['slots_taken_percent'], 50)

    def test_is_full_false_when_slots_available(self):
        """is_full is False when slots remain."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 5}}
        )
        self.assertFalse(s.data['is_full'])

    def test_is_full_true_when_no_slots(self):
        """is_full is True when all slots taken."""
        s = NGOEmployeeListSerializer(
            self.ngo,
            context={'registration_counts': {str(self.ngo.id): 20}}
        )
        self.assertTrue(s.data['is_full'])

    def test_service_type_nested(self):
        """serviceType is nested with id and name."""
        s    = NGOEmployeeListSerializer(self.ngo, context={'registration_counts': {}})
        data = s.data['serviceType']
        self.assertIn('id', data)
        self.assertIn('name', data)
        self.assertEqual(data['name'], 'Education')

    def test_organizer_nested(self):
        """organizer is nested with id, company_name, description."""
        s    = NGOEmployeeListSerializer(self.ngo, context={'registration_counts': {}})
        data = s.data['organizer']
        self.assertIn('id', data)
        self.assertIn('company_name', data)
        self.assertEqual(data['company_name'], 'Edu Org')

    def test_missing_registration_counts_context(self):
        """Serializer handles missing registration_counts gracefully."""
        s = NGOEmployeeListSerializer(self.ngo, context={})
        self.assertEqual(s.data['slots_taken'], 0)
        self.assertEqual(s.data['available_slots'], self.ngo.max_slots)

    def test_detail_serializer_has_same_fields(self):
        """Detail serializer has at minimum all list serializer fields."""
        list_s   = NGOEmployeeListSerializer(self.ngo, context={})
        detail_s = NGOEmployeeDetailSerializer(self.ngo, context={})
        for field in list_s.data.keys():
            self.assertIn(field, detail_s.data)


# ─────────────────────────────────────────────
# 3. Employee API Endpoint Tests
# ─────────────────────────────────────────────

class NGOEmployeeAPITest(TestCase):
    """
    Topic 13.2 — API tests for employee NGO endpoints.
    Tests authentication, filtering, and response structure.
    """

    def setUp(self):
        self.client = APIClient()
        self.st     = make_service_type('Environmental')
        self.org    = make_organizer('Eco Org')
        self.ngo1   = make_ngo(
            name         = 'Beach Cleanup',
            max_slots    = 15,
            service_type = self.st,
            organizer    = self.org,
        )
        self.ngo2 = make_ngo(
            name         = 'Tree Planting',
            max_slots    = 20,
            service_type = self.st,
            organizer    = self.org,
        )
        self.ngo_inactive = make_ngo(
            name         = 'Hidden NGO',
            is_active    = False,
            service_type = self.st,
            organizer    = self.org,
        )

    def _set_employee_auth(self, user_id=5):
        token = employee_token(user_id=user_id)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _set_admin_auth(self):
        token = admin_token()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    # ── Authentication tests ──────────────────

    def test_list_activities_requires_auth(self):
        response = self.client.get('/api/v1/activities/')
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,  # ← accept 403 too since AnonymousUser fails permission
        ])

    def test_list_activities_employee_can_access(self):
        """13.2 — Employee can list activities."""
        self._set_employee_auth()
        response = self.client.get('/api/v1/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_activities_admin_cannot_access_employee_endpoint(self):
        """Edge case — admin token rejected from employee endpoint."""
        self._set_admin_auth()
        response = self.client.get('/api/v1/activities/')
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ])

    # ── Response structure tests ──────────────

    def test_list_activities_returns_results(self):
        """13.2 — Activity list response has results."""
        self._set_employee_auth()
        response = self.client.get('/api/v1/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        results = data.get('results', data)
        self.assertIsInstance(results, list)

    def test_list_activities_only_active(self):
        """13.3 — Inactive NGOs are not shown to employees."""
        self._set_employee_auth()
        response  = self.client.get('/api/v1/activities/')
        data      = response.data
        results   = data.get('results', data)
        ngo_names = [n['name'] for n in results]
        self.assertNotIn('Hidden NGO', ngo_names)

    def test_activity_detail_employee_can_access(self):
        """13.2 — Employee can get activity detail."""
        self._set_employee_auth()
        response = self.client.get(f'/api/v1/activities/{self.ngo1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_activity_detail_not_found(self):
        """Edge case — non-existent activity returns 404."""
        self._set_employee_auth()
        response = self.client.get('/api/v1/activities/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activity_detail_contains_required_fields(self):
        """13.2 — Activity detail has required fields."""
        self._set_employee_auth()
        response = self.client.get(f'/api/v1/activities/{self.ngo1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data', response.data)
        for field in ['id', 'name', 'location', 'service_date',
                      'max_slots', 'status', 'is_full', 'is_closed']:
            self.assertIn(field, data, f"Missing field: {field}")

    # ── Filter tests ──────────────────────────

    def test_filter_by_service_date(self):
        """13.2 — Filter by service_date returns correct NGOs."""
        self._set_employee_auth()
        target_date = (date.today() + timedelta(days=30)).isoformat()
        response    = self.client.get(
            '/api/v1/activities/',
            {'service_date': target_date}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_service_type(self):
        """13.2 — Filter by service_type returns correct results."""
        self._set_employee_auth()
        response = self.client.get(
            '/api/v1/activities/',
            {'service_type': self.st.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_search_by_name(self):
        """13.2 — Search by name returns matching NGOs."""
        self._set_employee_auth()
        response = self.client.get(
            '/api/v1/activities/',
            {'search': 'Beach'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data    = response.data
        results = data.get('results', data)
        names   = [n['name'] for n in results]
        self.assertIn('Beach Cleanup', names)

    def test_employee_cannot_create_ngo(self):
        """Edge case — employee cannot POST to create NGO."""
        self._set_employee_auth()
        response = self.client.post('/api/v1/activities/', {
            'name': 'Unauthorized NGO',
        })
        self.assertIn(response.status_code, [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_401_UNAUTHORIZED,
        ])

    def test_employee_cannot_delete_ngo(self):
        """Edge case — employee cannot DELETE an NGO."""
        self._set_employee_auth()
        response = self.client.delete(f'/api/v1/activities/{self.ngo1.id}/')
        self.assertIn(response.status_code, [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_401_UNAUTHORIZED,
        ])


# ─────────────────────────────────────────────
# 4. Integration Tests
# ─────────────────────────────────────────────

class NGOEmployeeIntegrationTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.st     = make_service_type('Welfare')
        self.org    = make_organizer('Welfare Org')
        token       = employee_token(user_id=10)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        #clear cache so view fetches fresh from DB
        from django.core.cache import cache
        cache.clear()

    def test_newly_created_ngo_appears_in_list(self):
        """13.3 — NGO created in DB appears in API response."""
        from django.core.cache import cache
        cache.clear()  # ← clear again after creating NGO
        ngo      = make_ngo(name='New Welfare Drive',
                            service_type=self.st, organizer=self.org)
        cache.clear()  # ← clear so list picks up new NGO
        response = self.client.get('/api/v1/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data    = response.data
        results = data.get('results', data)
        names   = [n['name'] for n in results]
        self.assertIn('New Welfare Drive', names)

    def test_deactivated_ngo_disappears_from_list(self):
        """13.3 — Deactivated NGO no longer appears in employee list."""
        ngo = make_ngo(
            name='Active NGO',
            is_active=True,
            service_type=self.st,
            organizer=self.org
        )
        ngo.is_active = False
        ngo.save()

        response = self.client.get('/api/v1/activities/')
        data     = response.data
        results  = data.get('results', data)
        names    = [n['name'] for n in results]
        self.assertNotIn('Active NGO', names)

    def test_ngo_detail_reflects_db_data(self):
        """13.3 — Detail API response matches database record."""
        ngo      = make_ngo(
            name='Detail Test NGO',
            max_slots=25,
            service_type=self.st,
            organizer=self.org
        )
        response = self.client.get(f'/api/v1/activities/{ngo.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data', response.data)
        self.assertEqual(data['name'],      'Detail Test NGO')
        self.assertEqual(data['max_slots'], 25)
        self.assertEqual(data['location'],  'Kuala Lumpur')

    def test_closed_ngo_shows_correct_status(self):
        """13.3 — Closed NGO shows 'closed' status via API."""
        ngo = NGO.objects.create(
            name            = 'Past Cutoff NGO',
            description     = 'desc',
            serviceType     = self.st,
            organizer       = self.org,
            location        = 'KL',
            service_date    = date.today() + timedelta(days=5),
            start_time      = time(9, 0),
            end_time        = time(17, 0),
            max_slots       = 10,
            cutoff_datetime = timezone.now() - timedelta(hours=1),
            is_active       = True,
        )
        response = self.client.get(f'/api/v1/activities/{ngo.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data', response.data)
        self.assertEqual(data['status'], 'closed')
        self.assertTrue(data['is_closed'])

    def test_multiple_ngos_all_returned(self):
        """13.3 — Multiple NGOs in DB all returned in list."""
        from django.core.cache import cache
        make_ngo(name='NGO A', service_type=self.st, organizer=self.org)
        make_ngo(name='NGO B', service_type=self.st, organizer=self.org)
        make_ngo(name='NGO C', service_type=self.st, organizer=self.org)
        cache.clear()  # ← clear so all NGOs are fetched fresh

        response = self.client.get('/api/v1/activities/')
        data     = response.data
        results  = data.get('results', data)
        names    = [n['name'] for n in results]
        self.assertIn('NGO A', names)
        self.assertIn('NGO B', names)
        self.assertIn('NGO C', names)