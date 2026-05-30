import hashlib

from datetime import datetime, time as dt_time

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .bgg import fetch_bgg_game, fetch_bgg_weight, search_bgg, weight_to_complexity
from .borda import calculate_borda_scores
from .activity_feed import (
    record_event_created,
    record_event_created_batch,
    record_event_updated,
    record_member_joined,
    get_feed_for_user,
)
from .forms import (
    BetaAccessForm, BoardGameForm, ChangePasswordForm, EventForm, EventInviteForm, EventSettingsForm,
    FeedbackForm, FEEDBACK_TYPE_CHOICES,
    GroupCreateForm, GroupSettingsForm,
    PasswordResetForm, PrivateEventForm, RecurringEventForm, SetPasswordForm,
    SettingsForm, SuccessorPickForm,
    UserAddForm, UserManageForm, RegistrationForm, VerifiedIconForm,
)
from .models import BoardGame, Block, Event, EventAttendance, EventGameOverride, EventInvite, EventPresence, EventTag, GameOwnershipProposal, GameSession, GameSessionPlayer, GameTag, Group, GroupCreationLog, GroupInvite, GroupJoinRequest, GroupMembership, Friendship, Notification, PasswordHistory, PrivateEventCreationLog, SiteSettings, TagRequest, VerifiedIcon, Vote
from .models import TAG_MAX_LENGTH
from .notifications import (
    generate_missing_complexity_notifications,
    generate_missing_max_players_notifications,
    notify_event_invite_accepted,
    notify_event_invite_declined,
    notify_event_invite_sent,
    notify_event_organizer_designated,
    notify_event_co_creator,
    notify_group_demoted_member,
    notify_group_demoted_organizer,
    notify_group_game_added,
    notify_group_game_deleted,
    notify_group_event_created,
    notify_group_event_updated,
    notify_group_grace_period,
    notify_group_invite_created,
    notify_group_join_approved,
    notify_group_join_rejected,
    notify_group_member_joined,
    notify_group_member_left,
    notify_group_join_request,
    notify_group_promoted_admin,
    notify_group_promoted_organizer,
    notify_group_removed,
    notify_group_restored,
    notify_group_settings_changed,
    notify_group_voting_ended,
    notify_group_voting_resumed,
)
from .permissions import (
    can_create_event,
    can_create_group,
    can_create_private_event,
    can_delete_group,
    can_edit_group_settings,
    can_edit_private_event_settings,
    can_invite_to_event,
    can_restore_group,
    can_rsvp_private_event,
    can_view_game,
    can_view_group,
    can_view_private_event,
    is_group_admin,
    is_group_member,
    is_group_organizer,
)


def save_password_history(user, password):
    PasswordHistory.objects.create(user=user, password=password)
    history = PasswordHistory.objects.filter(user=user).order_by('-created_at')[5:]
    for record in history:
        record.delete()


def is_protected_user(user):
    protected = getattr(settings, 'PROTECTED_USERNAMES', '')
    if not protected:
        return False
    return user.username in [u.strip() for u in protected.split(',') if u.strip()]


def _password_state_component(user):
    return hashlib.sha256(user.password.encode()).hexdigest()[:16]


def generate_password_token(user):
    signer = TimestampSigner()
    return signer.sign(f"{user.pk}|{_password_state_component(user)}|{user.reset_token_version}")


def verify_password_token(token, max_age):
    signer = TimestampSigner()
    try:
        raw = signer.unsign(token, max_age=max_age)
    except Exception:
        return None
    parts = raw.split('|')
    if len(parts) != 3:
        if len(parts) == 2:
            return None
        return None
    pk_str, pw_hash, version_str = parts
    user = User.objects.filter(pk=pk_str).first()
    if not user:
        return None
    if _password_state_component(user) != pw_hash:
        return None
    try:
        if user.reset_token_version != int(version_str):
            return None
    except (ValueError, TypeError):
        return None
    return user
from .timezone_utils import is_valid_timezone
from .utils import parse_bgg_link, resize_group_image, resize_profile_picture

User = get_user_model()


def _process_bgg_link(game, form):
    bgg_id = form.cleaned_data.get('bgg_id')
    bgg_link_input = form.cleaned_data.get('bgg_link_input', '')

    if bgg_id:
        bgg_data = fetch_bgg_game(bgg_id)
        if bgg_data:
            game.bgg_id = bgg_data['bgg_id']
            game.bgg_link = bgg_data['bgg_link']
            game.image_url = bgg_data.get('image_url') or ''
            game.bgg_last_synced = timezone.now()
        weight = fetch_bgg_weight(bgg_id)
        if weight is not None:
            game.bgg_weight = weight
            if not game.complexity:
                game.complexity = weight_to_complexity(weight)
    elif bgg_link_input and bgg_link_input.strip():
        parsed = parse_bgg_link(bgg_link_input)
        if parsed:
            game.bgg_id = parsed['bgg_id']
            game.bgg_link = parsed['bgg_link']
            bgg_data = fetch_bgg_game(parsed['bgg_id'])
            if bgg_data:
                game.bgg_link = bgg_data['bgg_link'] or game.bgg_link
                game.image_url = bgg_data.get('image_url') or ''
                game.bgg_last_synced = timezone.now()
            weight = fetch_bgg_weight(parsed['bgg_id'])
            if weight is not None:
                game.bgg_weight = weight
                if not game.complexity:
                    game.complexity = weight_to_complexity(weight)
    else:
        game.bgg_id = None
        game.bgg_link = ''
        game.image_url = ''
        game.bgg_weight = None
        game.bgg_last_synced = None


class CustomLoginView(auth_views.LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        generate_missing_complexity_notifications(self.request.user)
        generate_missing_max_players_notifications(self.request.user)
        return response


MANAGE_USERS_ALLOWED_FIELDS = {'is_site_admin'}


def site_admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not (request.user.is_superuser or request.user.is_site_admin):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_manage_queryset(request):
    qs = User.objects.all()
    if not request.user.is_superuser:
        qs = qs.exclude(is_site_admin=True)
    return qs


@site_admin_required
def manage_users(request):
    active_qs = _get_manage_queryset(request).filter(deleted_at__isnull=True)
    deleted_qs = _get_manage_queryset(request).filter(deleted_at__isnull=False)
    tab = request.GET.get('tab', 'active')
    return render(request, 'club/manage_users.html', {
        'users': active_qs.order_by('username'),
        'deleted_users': deleted_qs.order_by('-deleted_at'),
        'is_superuser': request.user.is_superuser,
        'tab': tab,
    })


@site_admin_required
def manage_users_confirm(request):
    if request.method != 'POST':
        return redirect('manage_users')

    changes = request.session.pop('pending_role_changes', {})
    if not isinstance(changes, dict):
        return redirect('manage_users')

    allowed_user_ids = set(
        _get_manage_queryset(request)
        .filter(deleted_at__isnull=True)
        .values_list('pk', flat=True)
    )

    for user_id, role_changes in changes.items():
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            continue

        if uid not in allowed_user_ids:
            continue

        if not isinstance(role_changes, dict):
            continue

        safe_changes = {
            k: v for k, v in role_changes.items()
            if k in MANAGE_USERS_ALLOWED_FIELDS and isinstance(v, bool)
        }
        if safe_changes:
            User.objects.filter(pk=uid).update(**safe_changes)

    return redirect('manage_users')


@site_admin_required
def manage_users_cancel(request):
    request.session.pop('pending_role_changes', None)
    return redirect('manage_users')


@site_admin_required
def user_add(request):
    if request.method == 'POST':
        form = UserAddForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            temp_pw = form.cleaned_data.get('temporary_password')
            if temp_pw:
                user.set_password(temp_pw)
                user.must_change_password = True
                user.email_verified = False
                user.save()
                save_password_history(user, user.password)
            else:
                user.set_unusable_password()
                user.email_verified = False
                user.save()
            if user.email:
                token = generate_password_token(user)
                set_pw_url = request.build_absolute_uri(f'/set-password/{token}/')
                send_mail(
                    'Set your password - Board Game Club',
                    f'An account has been created for you. Set your password here: {set_pw_url}',
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            return redirect('manage_users')
    else:
        form = UserAddForm()
    return render(request, 'club/manage_users_add.html', {'form': form})


@site_admin_required
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser or user.pk == request.user.pk:
        raise PermissionDenied
    if not request.user.is_superuser and user.is_site_admin:
        raise PermissionDenied
    if request.method == 'POST':
        confirm_username = request.POST.get('confirm_username', '').strip()
        if confirm_username != user.username:
            return render(request, 'club/manage_users_delete.html', {
                'target_user': user,
                'error': True,
            })
        user.is_active = False
        user.deleted_at = timezone.now()
        user.deleted_by = request.user
        user.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])
        return redirect('manage_users')
    return render(request, 'club/manage_users_delete.html', {'target_user': user})


@site_admin_required
def user_restore(request, pk):
    user = get_object_or_404(User, pk=pk, deleted_at__isnull=False)
    if request.method == 'POST':
        user.is_active = True
        user.deleted_at = None
        user.deleted_by = None
        user.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])
        return redirect('manage_users')
    return render(request, 'club/manage_users_restore.html', {'target_user': user})


def user_permanent_delete(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    user = get_object_or_404(User, pk=pk, deleted_at__isnull=False)
    if request.method == 'POST':
        confirm_username = request.POST.get('confirm_username', '').strip()
        if confirm_username != user.username:
            return render(request, 'club/manage_users_permanent_delete.html', {
                'target_user': user,
                'error': True,
            })
        user.delete()
        return redirect('manage_users')
    return render(request, 'club/manage_users_permanent_delete.html', {'target_user': user})


def user_set_password(request, token):
    user = verify_password_token(token, max_age=86400 * 3)
    if user is None:
        return render(request, 'registration/set_password.html', {
            'form': None,
            'invalid_token': True,
        })

    if is_protected_user(user):
        return render(request, 'registration/set_password.html', {
            'form': None,
            'protected': True,
        })

    if request.method == 'POST':
        form = SetPasswordForm(request.POST, user=user)
        if form.is_valid():
            old_password = user.password
            user.password = make_password(form.cleaned_data['new_password1'])
            user.email_verified = True
            user.save()
            save_password_history(user, old_password)
            return render(request, 'registration/set_password.html', {
                'form': None,
                'success': True,
            })
    else:
        form = SetPasswordForm(user=user)

    return render(request, 'registration/set_password.html', {
        'form': form,
        'invalid_token': False,
    })


def forced_password_change(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.must_change_password:
        return redirect('dashboard')

    if is_protected_user(request.user):
        return render(request, 'club/forced_password_change.html', {
            'form': None,
            'protected': True,
        })

    if request.method == 'POST':
        form = SetPasswordForm(request.POST, user=request.user)
        if form.is_valid():
            new_pw = form.cleaned_data['new_password1']
            if check_password(new_pw, request.user.password):
                form.add_error(
                    'new_password1',
                    'Your new password must be different from your temporary password.',
                )
            else:
                old_password = request.user.password
                request.user.set_password(new_pw)
                request.user.must_change_password = False
                request.user.save()
                save_password_history(request.user, old_password)
                login(request, request.user)
                return redirect('dashboard')
    else:
        form = SetPasswordForm(user=request.user)

    return render(request, 'club/forced_password_change.html', {'form': form})


def beta_access(request):
    beta_hash = getattr(settings, 'BETA_ACCESS_CODE_HASH', '')
    if not beta_hash:
        return redirect('dashboard')

    if request.method == 'POST':
        form = BetaAccessForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['access_code']
            if check_password(code, beta_hash):
                response = redirect('dashboard')
                signer = TimestampSigner()
                signed = signer.sign('granted')
                response.set_cookie(
                    'beta_access',
                    signed,
                    max_age=90 * 86400,
                    httponly=True,
                    secure=not settings.DEBUG,
                    samesite='Lax',
                )
                return response
            form.add_error('access_code', 'Invalid access code.')
    else:
        form = BetaAccessForm()

    return render(request, 'club/beta_access.html', {'form': form})


def password_reset(request):
    import random
    import time

    from django.core.cache import cache

    submitted = False

    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email_or_username = form.cleaned_data['email_or_username']
            cache_key = f'password_reset_rl_{email_or_username.lower()}'
            submitted = True

            if not cache.get(cache_key):
                user = User.objects.filter(
                    Q(email__iexact=email_or_username) | Q(username__iexact=email_or_username)
                ).first()

                if user and user.email and not is_protected_user(user):
                    User.objects.filter(pk=user.pk).update(
                        reset_token_version=F('reset_token_version') + 1
                    )
                    user.refresh_from_db()
                    token = generate_password_token(user)
                    reset_url = request.build_absolute_uri(f'/password_reset/{token}/')
                    send_mail(
                        'Password Reset - Board Game Club',
                        f'Reset your password here: {reset_url}',
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                    )

                cache.set(cache_key, True, 120)

            time.sleep(random.uniform(0.1, 0.3))
        form = PasswordResetForm()
    else:
        form = PasswordResetForm()
    return render(request, 'registration/password_reset.html', {
        'form': form,
        'submitted': submitted,
    })


def password_reset_form(request, token):
    user = verify_password_token(token, max_age=3600)
    if user is None:
        return render(request, 'registration/password_reset_form.html', {
            'form': None,
            'invalid_token': True,
        })

    if is_protected_user(user):
        return render(request, 'registration/password_reset_form.html', {
            'form': None,
            'protected': True,
        })

    if request.method == 'POST':
        form = SetPasswordForm(request.POST, user=user)
        if form.is_valid():
            old_password = user.password
            user.password = make_password(form.cleaned_data['new_password1'])
            user.save()
            save_password_history(user, old_password)
            return render(request, 'registration/password_reset_done.html')
    else:
        form = SetPasswordForm(user=user)

    return render(request, 'registration/password_reset_form.html', {
        'form': form,
        'invalid_token': False,
    })


def dashboard(request):
    if not request.user.is_authenticated:
        return render(request, 'club/dashboard.html')

    from django.db.models import Q as _Q

    memberships = GroupMembership.objects.filter(
        user=request.user,
        group__disbanded_at__isnull=True,
    ).select_related('group').order_by('-is_favorite', 'group__name')
    my_groups = [m.group for m in memberships]

    my_games = BoardGame.objects.filter(
        owner=request.user,
    ).order_by('name')[:5]

    upcoming_events = Event.objects.filter(
        group__membership__user=request.user,
        group__disbanded_at__isnull=True,
        end_time__gte=timezone.now(),
    ).select_related('created_by', 'group').order_by('date')[:5]

    recent_activities = get_feed_for_user(request.user, limit=10, days=7)

    return render(request, 'club/dashboard.html', {
        'my_groups': my_groups,
        'my_games': my_games,
        'upcoming_events': upcoming_events,
        'recent_activities': recent_activities,
    })


@login_required
def activity_feed(request):
    from django.core.paginator import Paginator
    all_activities = get_feed_for_user(request.user)
    paginator = Paginator(all_activities, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'club/activity_feed.html', {
        'activities': page_obj.object_list,
        'page_obj': page_obj,
    })


def public_profile(request, username):
    if not request.user.is_authenticated:
        return redirect('/login/')
    profile_user = get_object_or_404(User, username__iexact=username)

    if profile_user.is_superuser and request.user != profile_user:
        raise Http404

    is_own = request.user == profile_user

    context = {
        'profile_user': profile_user,
        'is_own': is_own,
    }

    is_blocked = (
        not is_own
        and Block.is_blocked(request.user, profile_user)
    )
    context['is_blocked'] = is_blocked

    if is_blocked:
        return render(request, 'club/profile.html', context)

    if is_own or profile_user.show_games:
        context['games'] = BoardGame.objects.filter(
            owner=profile_user,
        ).select_related('owner')

    if is_own or profile_user.show_events:
        attendances = EventAttendance.objects.filter(
            user=profile_user,
        ).select_related('event', 'event__created_by')
        context['attendances'] = attendances

    context['show_date_joined'] = is_own or profile_user.show_date_joined

    if not is_own:
        friendship = Friendship.get_friendship(request.user, profile_user)
        if friendship is None:
            context['friend_status'] = 'none'
            context['friendship'] = None
        elif friendship.status == 'accepted':
            context['friend_status'] = 'friends'
            context['friendship'] = friendship
        elif friendship.status == 'pending':
            if friendship.requester == request.user:
                context['friend_status'] = 'pending_sent'
            else:
                context['friend_status'] = 'pending_received'
            context['friendship'] = friendship
        elif friendship.status == 'declined':
            context['friend_status'] = 'none'
            context['friendship'] = None
    else:
        context['friend_status'] = None
        context['friendship'] = None

    return render(request, 'club/profile.html', context)


def user_settings(request):
    if not request.user.is_authenticated:
        return redirect('/login/')

    if request.method == 'POST':
        form = SettingsForm(request.POST, request.FILES)
        if form.is_valid():
            new_email = form.cleaned_data['email']
            new_tz = form.cleaned_data['timezone']
            new_icon = form.cleaned_data.get('verified_icon')
            new_bio = form.cleaned_data.get('bio', '')
            new_picture = form.cleaned_data.get('profile_picture')
            new_show_games = form.cleaned_data.get('show_games', True)
            new_show_events = form.cleaned_data.get('show_events', True)
            new_show_date_joined = form.cleaned_data.get('show_date_joined', True)
            new_show_friends = form.cleaned_data.get('show_friends', True)
            new_show_in_search = form.cleaned_data.get('show_in_search', True)
            new_theme = form.cleaned_data.get('theme', 'system')
            user = request.user

            email_changed = new_email != user.email
            tz_changed = new_tz != user.timezone
            old_icon_id = user.verified_icon_id
            new_icon_id = new_icon.pk if new_icon else None
            icon_changed = old_icon_id != new_icon_id
            bio_changed = new_bio != user.bio
            privacy_changed = (
                new_show_games != user.show_games
                or new_show_events != user.show_events
                or new_show_date_joined != user.show_date_joined
                or new_show_friends != user.show_friends
                or new_show_in_search != user.show_in_search
            )
            theme_changed = new_theme != user.theme

            if email_changed:
                user.email = new_email
                if new_email:
                    user.email_verified = False
                else:
                    user.email_verified = False

            if tz_changed:
                user.timezone = new_tz
                user.timezone_detected = False

            if user.email_verified:
                user.verified_icon = new_icon

            if bio_changed:
                user.bio = new_bio

            if new_picture:
                buffer = resize_profile_picture(new_picture)
                user.profile_picture.save(
                    f'{user.username}_profile.jpg',
                    buffer,
                    save=False,
                )

            user.show_games = new_show_games
            user.show_events = new_show_events
            user.show_date_joined = new_show_date_joined
            user.show_friends = new_show_friends
            user.show_in_search = new_show_in_search

            if theme_changed:
                user.theme = new_theme

            if email_changed or tz_changed or icon_changed or bio_changed or new_picture or privacy_changed or theme_changed:
                user.save()
                if email_changed and new_email:
                    signer = TimestampSigner()
                    token = signer.sign(user.pk)
                    verify_url = request.build_absolute_uri(f'/verify-email/{token}/')
                    send_mail(
                        'Verify your email - Board Game Club',
                        f'Click the link to verify your email: {verify_url}',
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                    )

            return redirect('user_settings')
    else:
        form = SettingsForm(initial={
            'email': request.user.email,
            'timezone': request.user.timezone or 'UTC',
            'verified_icon': request.user.verified_icon_id or '',
            'bio': request.user.bio or '',
            'show_games': request.user.show_games,
            'show_events': request.user.show_events,
            'show_date_joined': request.user.show_date_joined,
            'show_friends': request.user.show_friends,
            'show_in_search': request.user.show_in_search,
            'theme': request.user.theme or 'system',
        })

    return render(request, 'club/settings.html', {
        'form': form,
        'verified_icons': VerifiedIcon.objects.all().order_by('name'),
        'blocked_users': User.objects.filter(
            pk__in=Block.objects.filter(
                blocker=request.user,
            ).values_list('blocked_id', flat=True),
        ).order_by('username'),
    })


@login_required
def remove_email(request):
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    user = request.user
    user.email = ''
    user.email_verified = False
    user.verified_icon = None
    user.save(update_fields=['email', 'email_verified', 'verified_icon'])
    return redirect('user_settings')


def change_password(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.user.is_superuser:
        raise PermissionDenied

    if request.method == 'POST':
        form = ChangePasswordForm(request.POST, user=request.user)
        if form.is_valid():
            old_password = request.user.password
            new_password = form.cleaned_data['new_password1']
            request.user.set_password(new_password)
            request.user.save()
            save_password_history(request.user, old_password)
            login(request, request.user)
            return redirect(reverse('user_settings') + '?password_changed=1')
    else:
        form = ChangePasswordForm(user=request.user)

    return render(request, 'club/change_password.html', {'form': form})


def save_timezone(request):
    if request.method != 'POST':
        return redirect('dashboard')
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.user.timezone_detected:
        return redirect('dashboard')

    tz_name = request.POST.get('timezone', '')
    if is_valid_timezone(tz_name):
        request.user.timezone = tz_name
        request.user.timezone_detected = True
        request.user.save(update_fields=['timezone', 'timezone_detected'])
    next_url = request.POST.get('next', 'dashboard')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts=settings.ALLOWED_HOSTS, require_https=True):
        return redirect(next_url)
    return redirect('dashboard')


def register(request):
    site_settings = SiteSettings.load()
    if site_settings.site_lockdown_active:
        if not (request.user.is_authenticated and request.user.is_superuser):
            return redirect('/login/')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            if not user.email:
                user.email_verified = False
                user.save()
                login(request, user)
                return redirect('dashboard')
            if settings.REQUIRE_EMAIL_VERIFICATION:
                signer = TimestampSigner()
                token = signer.sign(user.pk)
                verify_url = request.build_absolute_uri(f'/verify-email/{token}/')
                send_mail(
                    'Verify your email - Board Game Club',
                    f'Click the link to verify your email: {verify_url}',
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
                return render(request, 'registration/verify_email_sent.html', {'email': user.email})
            else:
                user.email_verified = True
                user.save()
                login(request, user)
                return redirect('dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


def verify_email(request, token):
    signer = TimestampSigner()
    try:
        user_pk = signer.unsign(token, max_age=86400)
    except Exception:
        return render(request, 'registration/verify_email_confirmed.html', {'success': False})

    user = get_object_or_404(User, pk=user_pk)
    if not user.email_verified:
        user.email_verified = True
        user.save()
    return render(request, 'registration/verify_email_confirmed.html', {'success': True})


def bgg_search(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse([], safe=False)
    results = search_bgg(query)
    return JsonResponse(results, safe=False)


def bgg_import(request, bgg_id):
    if not request.user.is_authenticated:
        return redirect('/login/')
    data = fetch_bgg_game(bgg_id)
    if data is None:
        return JsonResponse({'error': 'Game not found on BoardGameGeek'})
    weight = fetch_bgg_weight(bgg_id)
    if weight is not None:
        data['bgg_weight'] = str(weight)
        data['suggested_complexity'] = weight_to_complexity(weight)
    return JsonResponse(data)


def _compute_game_details(games, user):
    is_admin = user.is_superuser or user.is_site_admin
    role_priority = {'admin': 0, 'organizer': 1, 'member': 2}

    group_info = {}
    if not is_admin:
        memberships = GroupMembership.objects.filter(
            user=user,
        ).select_related('group').values(
            'group_id', 'group__name', 'group__slug', 'role', 'is_favorite',
        )
        for m in memberships:
            group_info[m['group_id']] = {
                'name': m['group__name'],
                'slug': m['group__slug'],
                'role_priority': role_priority.get(m['role'], 3),
                'is_favorite': m['is_favorite'],
            }

    owner_group_map = {}
    if not is_admin:
        other_owner_ids = set()
        for g in games:
            if g.owner_id and g.owner_id != user.pk:
                other_owner_ids.add(g.owner_id)
        if other_owner_ids and group_info:
            owner_group_pairs = GroupMembership.objects.filter(
                user_id__in=other_owner_ids,
                group_id__in=group_info.keys(),
                role__in=['admin', 'organizer', 'member'],
            ).values_list('user_id', 'group_id')
            for uid, gid in owner_group_pairs:
                owner_group_map.setdefault(uid, set()).add(gid)

    game_details = {}
    for game in games:
        if game.owner_id == user.pk:
            game_details[game.pk] = {'owned_by': 'self', 'details': []}
            continue

        details = []

        if game.owner_id is None and game.group_id is not None:
            gi = group_info.get(game.group_id)
            if gi:
                details.append({
                    'group_name': gi['name'],
                    'group_slug': gi['slug'],
                    'owner_display': 'Group Owned',
                    'sort_key': (gi['role_priority'], 0 if gi['is_favorite'] else 1, gi['name']),
                })
            else:
                details.append({
                    'group_name': game.group.name if game.group else 'Unknown',
                    'group_slug': game.group.slug if game.group else '',
                    'owner_display': 'Group Owned',
                    'sort_key': (3, 1, game.group.name if game.group else 'zzz'),
                })
        elif game.owner_id is not None:
            if not is_admin:
                shared_groups = owner_group_map.get(game.owner_id, set()) & set(group_info.keys())
            else:
                shared_groups = set()
            if shared_groups:
                for gid in shared_groups:
                    gi = group_info[gid]
                    details.append({
                        'group_name': gi['name'],
                        'group_slug': gi['slug'],
                        'owner_display': game.owner.username,
                        'sort_key': (gi['role_priority'], 0 if gi['is_favorite'] else 1, gi['name'], game.owner.username),
                    })
            else:
                if game.group_id is not None:
                    group_name = game.group.name if game.group else None
                    group_slug = game.group.slug if game.group else ''
                    details.append({
                        'group_name': group_name,
                        'group_slug': group_slug,
                        'owner_display': game.owner.username,
                        'sort_key': (3, 1, group_name or 'zzz', game.owner.username),
                    })
                else:
                    details.append({
                        'group_name': None,
                        'group_slug': '',
                        'owner_display': game.owner.username,
                        'sort_key': (3, 1, 'zzz', game.owner.username),
                    })

        details.sort(key=lambda x: x['sort_key'])
        game_details[game.pk] = {'owned_by': 'others', 'details': details}

    return game_details


def game_list(request):
    if not request.user.is_authenticated:
        return redirect('/login/')

    is_admin_user = request.user.is_superuser or request.user.is_site_admin

    if is_admin_user:
        base_games = BoardGame.objects.select_related('owner', 'group').all()
    else:
        user_group_ids = set(GroupMembership.objects.filter(
            user=request.user,
        ).values_list('group_id', flat=True))

        event_user_ids = set()
        user_event_ids = set()
        user_event_ids.update(EventAttendance.objects.filter(
            user=request.user,
            event__group_id__isnull=True,
            event__is_active=True,
            event__end_time__gt=timezone.now(),
        ).values_list('event_id', flat=True))
        user_event_ids.update(Event.objects.filter(
            created_by=request.user,
            group_id__isnull=True,
            is_active=True,
            end_time__gt=timezone.now(),
        ).values_list('pk', flat=True))
        user_event_ids.update(Event.objects.filter(
            additional_organizers=request.user,
            group_id__isnull=True,
            is_active=True,
            end_time__gt=timezone.now(),
        ).values_list('pk', flat=True))
        if user_event_ids:
            event_user_ids = set(
                EventAttendance.objects.filter(event_id__in=user_event_ids)
                .values_list('user_id', flat=True)
            )
            event_user_ids.update(
                Event.objects.filter(pk__in=user_event_ids)
                .values_list('created_by_id', flat=True)
            )
            event_user_ids.update(
                get_user_model().objects.filter(
                    co_organized_events__pk__in=user_event_ids,
                ).values_list('pk', flat=True)
            )

        base_games = BoardGame.objects.select_related('owner', 'group').filter(
            Q(owner=request.user)
            | Q(group_id__in=user_group_ids)
            | Q(
                owner__membership__group_id__in=user_group_ids,
                owner__membership__role__in=['admin', 'organizer', 'member'],
            )
            | Q(owner_id__in=event_user_ids)
        ).distinct()

    visible_owners = User.objects.filter(
        boardgame__in=base_games,
    ).exclude(pk=request.user.pk).distinct().order_by('username').values_list('username', flat=True)

    if is_admin_user:
        visible_groups = list(Group.objects.filter(
            disbanded_at__isnull=True,
        ).order_by('name'))
    else:
        visible_groups = list(Group.objects.filter(
            membership__user=request.user,
            disbanded_at__isnull=True,
        ).order_by('name').distinct())

    games = base_games
    active_tab = request.GET.get('tab', 'all')

    if active_tab == 'my':
        games = games.filter(owner=request.user)

    owner_filter = request.GET.getlist('owner')
    if owner_filter:
        resolved_owners = []
        for o in owner_filter:
            if o == 'myself':
                resolved_owners.append(request.user.username)
            else:
                resolved_owners.append(o)
        if resolved_owners:
            games = games.filter(owner__username__in=resolved_owners)

    group_filter = request.GET.get('group', '')
    if group_filter == 'self':
        games = games.filter(owner=request.user)
    elif group_filter:
        group_obj = Group.objects.filter(slug=group_filter).first()
        if group_obj:
            games = games.filter(
                Q(group_id=group_obj.pk)
                | Q(
                    owner_id__isnull=False,
                    owner__membership__group_id=group_obj.pk,
                    owner__membership__role__in=['admin', 'organizer', 'member'],
                )
            ).exclude(owner=request.user)

    players_param = request.GET.get('players', '')
    if players_param:
        try:
            player_count = int(players_param)
            games = games.filter(
                Q(min_players__isnull=False, min_players__lte=player_count)
                & (Q(max_players=0) | Q(max_players__isnull=False, max_players__gte=player_count))
            )
        except (ValueError, TypeError):
            pass

    tag_param = request.GET.getlist('tag')
    if tag_param:
        if '__none__' in tag_param:
            games = games.filter(tags__isnull=True)
        else:
            games = games.filter(tags__name__in=tag_param).distinct()

    sort_param = request.GET.get('sort', 'name_asc')
    sort_map = {
        'name_asc': 'name',
        'name_desc': '-name',
        'min_players_asc': 'min_players',
        'min_players_desc': '-min_players',
        'max_players_asc': 'max_players',
        'max_players_desc': '-max_players',
        'owner_asc': 'owner__username',
        'owner_desc': '-owner__username',
    }
    order_by = sort_map.get(sort_param, 'name')
    games = games.order_by(order_by)

    game_details = _compute_game_details(games, request.user)
    for game in games:
        game.ownership_info = game_details.get(game.pk, {'owned_by': 'self', 'details': []})

    active_filter_count = 0
    if owner_filter:
        active_filter_count += 1
    if players_param:
        active_filter_count += 1
    if group_filter:
        active_filter_count += 1
    if tag_param:
        active_filter_count += 1

    return render(request, 'club/game_list.html', {
        'games': games,
        'active_tab': active_tab,
        'all_owners': visible_owners,
        'visible_groups': visible_groups,
        'current_sort': sort_param,
        'owner_filter': owner_filter,
        'players_filter': players_param,
        'group_filter': group_filter,
        'active_filter_count': active_filter_count,
        'all_game_tags': GameTag.objects.all(),
        'tag_filter': tag_param,
    })


def _get_user_org_groups(user):
    if not user.is_authenticated:
        return Group.objects.none()
    return Group.objects.filter(
        membership__user=user,
        membership__role__in=['admin', 'organizer'],
    ).distinct()


def _resolve_default_ownership(request):
    group_slug = request.GET.get('group', '')
    event_pk = request.GET.get('event', '')
    suggested_groups = ['self']
    default = 'self'

    if event_pk:
        try:
            event = Event.objects.get(pk=int(event_pk))
            if event.group_id is not None:
                group_slug = event.group.slug
        except (Event.DoesNotExist, ValueError, TypeError):
            pass

    if group_slug:
        try:
            group = Group.objects.get(slug=group_slug)
            if _get_user_org_groups(request.user).filter(pk=group.pk).exists():
                default = f'group:{group.slug}'
                if group.slug not in suggested_groups:
                    suggested_groups.append(group.slug)
        except Group.DoesNotExist:
            pass

    return default, suggested_groups


def _apply_ownership(game, ownership_target, user):
    if ownership_target and ownership_target.startswith('group:'):
        slug = ownership_target[len('group:'):]
        group = Group.objects.get(slug=slug)
        game.owner = None
        game.group = group
    else:
        game.owner = user
        game.group = None


def game_add(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    org_groups = _get_user_org_groups(request.user)
    default_ownership, suggested_groups = _resolve_default_ownership(request)
    if request.method == 'POST':
        form = BoardGameForm(request.POST, ownership_user=request.user)
        if form.is_valid():
            game = form.save(commit=False)
            ownership = form.cleaned_data.get('ownership_target', 'self') or 'self'
            _apply_ownership(game, ownership, request.user)
            _process_bgg_link(game, form)
            game.save()
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            if tag_id_list:
                game.tags.set(tag_id_list)
            if game.group:
                notify_group_game_added(game.group, game, request.user)
            return redirect('game_detail', pk=game.pk)
    else:
        form = BoardGameForm(ownership_user=request.user)
    return render(request, 'club/game_form.html', {
        'form': form,
        'action': 'Add',
        'initial_tags': [],
        'org_groups': org_groups,
        'default_ownership': default_ownership,
        'suggested_groups': suggested_groups,
        'current_ownership': default_ownership,
    })


def group_game_add(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if group.is_disbanded:
        raise PermissionDenied
    if not is_group_organizer(request.user, group):
        raise PermissionDenied
    if request.method == 'POST':
        form = BoardGameForm(request.POST, ownership_user=request.user)
        if form.is_valid():
            game = form.save(commit=False)
            ownership = form.cleaned_data.get('ownership_target', 'self') or 'self'
            _apply_ownership(game, ownership, request.user)
            _process_bgg_link(game, form)
            game.save()
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            if tag_id_list:
                game.tags.set(tag_id_list)
            notify_group_game_added(group, game, request.user)
            return redirect('game_detail', pk=game.pk)
        org_groups = _get_user_org_groups(request.user)
        return render(request, 'club/game_form.html', {
            'form': form,
            'action': 'Add Group Game',
            'group': group,
            'initial_tags': [],
            'org_groups': org_groups,
            'default_ownership': f'group:{group.slug}',
            'suggested_groups': ['self', group.slug],
            'current_ownership': f'group:{group.slug}',
        })
    return redirect(f'{reverse("game_add")}?group={group.slug}')


def game_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = BoardGame.objects.filter(pk=pk).first()
    if not game or not can_view_game(request.user, game):
        return render(request, 'club/game_not_available.html')
    can_edit = (
        game.owner == request.user
        or request.user.is_superuser
        or (game.group and is_group_organizer(request.user, game.group))
    )
    return render(request, 'club/game_detail.html', {
        'game': game,
        'can_edit_game': can_edit,
    })


def game_edit(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = BoardGame.objects.filter(pk=pk).first()
    if not game or not can_view_game(request.user, game):
        return render(request, 'club/game_not_available.html')
    is_superuser_editing_others = (
        request.user.is_superuser and game.owner != request.user
    )
    is_group_organizer_editing = (
        game.group
        and is_group_organizer(request.user, game.group)
    )
    is_group_admin_editing = (
        game.group
        and is_group_admin(request.user, game.group)
    )
    can_edit = (
        game.owner == request.user
        or is_superuser_editing_others
        or is_group_organizer_editing
        or is_group_admin_editing
    )
    if not can_edit:
        raise PermissionDenied

    org_groups = _get_user_org_groups(request.user)
    if game.owner_id is not None and game.group_id is None:
        current_ownership = 'self'
    elif game.group_id is not None:
        current_ownership = f'group:{game.group.slug}'
    else:
        current_ownership = 'self'

    if request.method == 'POST':
        form = BoardGameForm(request.POST, instance=game, ownership_user=request.user)
        if form.is_valid():
            ownership = form.cleaned_data.get('ownership_target', 'self') or 'self'
            old_ownership = current_ownership
            _process_bgg_link(game, form)
            form.save()
            if ownership != old_ownership:
                can_change = False
                if old_ownership == 'self' and ownership.startswith('group:'):
                    can_change = (game.owner == request.user) or is_superuser_editing_others
                elif old_ownership.startswith('group:') and ownership == 'self':
                    can_change = is_group_organizer_editing or is_group_admin_editing or is_superuser_editing_others
                elif old_ownership.startswith('group:') and ownership.startswith('group:'):
                    can_change = is_group_organizer_editing or is_group_admin_editing or is_superuser_editing_others
                if can_change:
                    _apply_ownership(game, ownership, request.user)
                    game.save()
                else:
                    form.add_error('ownership_target', 'You do not have permission to change ownership.')
                    return render(request, 'club/game_form.html', {
                        'form': form,
                        'action': 'Edit',
                        'is_superuser_editing_others': is_superuser_editing_others,
                        'game': game,
                        'initial_tags': list(game.tags.all()),
                        'org_groups': org_groups,
                        'default_ownership': ownership,
                        'current_ownership': old_ownership,
                        'suggested_groups': ['self'],
                    })
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            game.tags.set(tag_id_list)
            if game.complexity:
                Notification.objects.filter(
                    user=request.user,
                    notification_type='missing_complexity',
                    url=f'/games/{game.pk}/edit/',
                    is_read=False,
                ).update(is_read=True)
            if game.max_players is not None:
                Notification.objects.filter(
                    user=request.user,
                    notification_type='missing_max_players',
                    url=f'/games/{game.pk}/edit/',
                    is_read=False,
                ).update(is_read=True)
            return redirect('game_detail', pk=game.pk)
    else:
        form = BoardGameForm(instance=game, ownership_user=request.user)
    return render(request, 'club/game_form.html', {
        'form': form,
        'action': 'Edit',
        'is_superuser_editing_others': is_superuser_editing_others,
        'game': game,
        'initial_tags': list(game.tags.all()),
        'org_groups': org_groups,
        'default_ownership': current_ownership,
        'current_ownership': current_ownership,
        'suggested_groups': ['self'],
    })


def game_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = BoardGame.objects.filter(pk=pk).first()
    if not game or not can_view_game(request.user, game):
        return render(request, 'club/game_not_available.html')
    is_group_organizer_deleting = (
        game.group
        and is_group_organizer(request.user, game.group)
    )
    if (game.owner != request.user
            and not request.user.is_superuser
            and not is_group_organizer_deleting):
        raise PermissionDenied
    if request.method == 'POST':
        deleted_game_group = game.group
        deleted_game_name = game.name
        game.delete()
        if deleted_game_group:
            notify_group_game_deleted(deleted_game_group, deleted_game_name, request.user)
        return redirect('game_list')
    return render(request, 'club/game_confirm_delete.html', {
        'game': game,
        'is_superuser_deleting_others': request.user.is_superuser and game.owner != request.user,
    })


def event_list(request):
    tag_param = request.GET.getlist('tag')

    if not request.user.is_authenticated:
        groups = Group.objects.filter(discoverable=True, disbanded_at__isnull=True)
        group_events = Event.objects.filter(
            group__in=groups,
            end_time__gte=timezone.now(),
        ).select_related('created_by', 'group').order_by('date')
        if tag_param:
            if '__none__' in tag_param:
                group_events = group_events.filter(tags__isnull=True)
            else:
                group_events = group_events.filter(tags__name__in=tag_param).distinct()

        return render(request, 'club/event_list.html', {
            'group_events': group_events,
            'private_events': Event.objects.none(),
            'time_midnight': dt_time(0, 0),
            'all_event_tags': EventTag.objects.all(),
            'tag_filter': tag_param,
        })

    memberships = GroupMembership.objects.filter(
        user=request.user,
        group__disbanded_at__isnull=True,
    ).values_list('group_id', flat=True)

    group_events = Event.objects.filter(
        group_id__in=memberships,
        end_time__gte=timezone.now(),
    ).select_related('created_by', 'group').order_by('date')
    if tag_param:
        if '__none__' in tag_param:
            group_events = group_events.filter(tags__isnull=True)
        else:
            group_events = group_events.filter(tags__name__in=tag_param).distinct()

    private_events = Event.objects.filter(
        group__isnull=True,
        eventattendance__user=request.user,
        end_time__gte=timezone.now(),
    ).select_related('created_by').order_by('date')

    return render(request, 'club/event_list.html', {
        'group_events': group_events,
        'private_events': private_events,
        'time_midnight': dt_time(0, 0),
        'all_event_tags': EventTag.objects.all(),
        'tag_filter': tag_param,
    })


def discover_events(request):
    now = timezone.now()
    events = Event.objects.filter(
        group__isnull=True,
        privacy__in=['public', 'invite_only_public'],
        end_time__gte=now,
        is_active=True,
        ended_early_at__isnull=True,
    ).select_related('created_by')

    tag_param = request.GET.getlist('tag')
    if tag_param:
        if '__none__' in tag_param:
            events = events.filter(tags__isnull=True)
        else:
            events = events.filter(tags__name__in=tag_param).distinct()

    date_from = request.GET.get('date_from')
    if date_from:
        try:
            parsed_from = timezone.make_aware(
                datetime.strptime(date_from, '%Y-%m-%d')
            )
            events = events.filter(date__gte=parsed_from)
        except ValueError:
            pass

    date_to = request.GET.get('date_to')
    if date_to:
        try:
            parsed_to = timezone.make_aware(
                datetime.strptime(date_to, '%Y-%m-%d') + timezone.timedelta(days=1)
            )
            events = events.filter(date__lt=parsed_to)
        except ValueError:
            pass

    sort = request.GET.get('sort', 'asc')
    if sort == 'desc':
        events = events.order_by('-date')
    else:
        events = events.order_by('date')

    return render(request, 'club/discover_events.html', {
        'events': events,
        'time_midnight': dt_time(0, 0),
        'all_event_tags': EventTag.objects.all(),
        'tag_filter': tag_param,
        'date_from': date_from or '',
        'date_to': date_to or '',
        'sort': sort,
    })


def group_event_list(request, slug):
    if not request.user.is_authenticated:
        raise PermissionDenied
    group = get_object_or_404(Group, slug=slug)
    if not can_view_group(request.user, group):
        raise PermissionDenied
    is_organizer = (
        request.user.is_authenticated
        and is_group_organizer(request.user, group)
    )
    tag_param = request.GET.getlist('tag')
    events = Event.objects.filter(group=group).select_related('created_by', 'group').order_by('date')
    if tag_param:
        if '__none__' in tag_param:
            events = events.filter(tags__isnull=True)
        else:
            events = events.filter(tags__name__in=tag_param).distinct()
    return render(request, 'club/event_list.html', {
        'group_events': events,
        'private_events': Event.objects.none(),
        'time_midnight': dt_time(0, 0),
        'group': group,
        'is_group_organizer': is_organizer,
        'all_event_tags': EventTag.objects.all(),
        'tag_filter': tag_param,
    })


def group_games(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not can_view_group(request.user, group):
        raise PermissionDenied
    if group.is_disbanded:
        raise PermissionDenied
    is_organizer = is_group_organizer(request.user, group)
    all_games = group.games()
    total_count = all_games.count()
    games = all_games.select_related('owner', 'group').order_by('name')

    show_group_owned = request.GET.get('group_owned', '1') != '0'
    selected_owners = request.GET.getlist('owner')

    if not show_group_owned:
        games = games.filter(owner__isnull=False)
    if selected_owners:
        games = games.filter(owner__username__in=selected_owners)

    tag_param = request.GET.getlist('tag')
    if tag_param:
        if '__none__' in tag_param:
            games = games.filter(tags__isnull=True)
        else:
            games = games.filter(tags__name__in=tag_param).distinct()

    member_owners = User.objects.filter(
        boardgame__in=group.games().filter(owner__isnull=False),
    ).distinct().order_by('username')

    return render(request, 'club/group_games.html', {
        'group': group,
        'games': games,
        'is_organizer': is_organizer,
        'member_owners': member_owners,
        'show_group_owned': show_group_owned,
        'selected_owners': selected_owners,
        'total_count': total_count,
        'all_game_tags': GameTag.objects.all(),
        'tag_filter': tag_param,
    })


def event_add(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if not can_create_event(request.user, group):
        raise PermissionDenied
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.date = form.cleaned_data['date']
            event.created_by = request.user
            event.group = group
            offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0
            event.voting_deadline_offset_minutes = offset
            custom_deadline = form.cleaned_data.get('voting_deadline')
            if custom_deadline:
                event.voting_deadline = custom_deadline
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.duration_minutes = form.cleaned_data.get('duration_minutes') or 120
            event.save()
            record_event_created(event, request.user)
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            if tag_id_list:
                event.tags.set(tag_id_list)
            notify_group_event_created(group, event, request.user)
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
    else:
        form = EventForm(initial={
            'voting_deadline_offset_minutes': SiteSettings.load().default_voting_offset_minutes,
            'duration_minutes': group.default_event_duration_minutes,
        })
    return render(request, 'club/event_form.html', {
        'form': form,
        'action': 'Create',
        'voting_offset': SiteSettings.load().default_voting_offset_minutes,
        'group': group,
        'initial_tags': [],
    })


def _compute_recurring_dates(start_dt, end_type, occurrence_count, end_date):
    dates = []
    current = start_dt
    if end_type == 'count':
        for _ in range(occurrence_count):
            dates.append(current)
            current = current + timezone.timedelta(days=7)
    else:
        end_dt = timezone.make_aware(
            datetime.combine(end_date, dt_time(23, 59))
        ) if timezone.is_naive(datetime.combine(end_date, dt_time(23, 59))) else datetime.combine(
            end_date, dt_time(23, 59)
        )
        while current <= end_dt:
            dates.append(current)
            current = current + timezone.timedelta(days=7)
    return dates


def event_add_recurring(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if not can_create_event(request.user, group):
        raise PermissionDenied

    if request.method == 'POST':
        form = RecurringEventForm(request.POST)
        if form.is_valid():
            start_dt = form.cleaned_data['start_datetime']
            end_type = form.cleaned_data['end_type']
            occurrence_count = form.cleaned_data.get('occurrence_count') or 0
            end_date = form.cleaned_data.get('end_date')

            dates = _compute_recurring_dates(start_dt, end_type, occurrence_count, end_date)

            if not dates:
                form.add_error(None, 'No dates could be computed. Check your start date and end condition.')
                return render(request, 'club/event_form_recurring.html', {
                    'form': form,
                    'voting_offset': SiteSettings.load().default_voting_offset_minutes,
                    'group': group,
                })

            date_list = []
            for d in dates:
                date_list.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'time': d.strftime('%H:%M') if d.time() != dt_time(0, 0) else '',
                    'datetime': d.isoformat(),
                    'checked': True,
                })

            vd_date = form.cleaned_data.get('voting_deadline_date')
            vd_time = form.cleaned_data.get('voting_deadline_time')
            vd_offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0

            form_data = {
                'title': form.cleaned_data['title'],
                'description': form.cleaned_data.get('description', ''),
                'location': form.cleaned_data.get('location', ''),
                'time': form.cleaned_data.get('time').strftime('%H:%M') if form.cleaned_data.get('time') else '',
                'voting_deadline_offset_minutes': vd_offset,
                'voting_deadline_date': vd_date.strftime('%Y-%m-%d') if vd_date else '',
                'voting_deadline_time': vd_time.strftime('%H:%M') if vd_time else '',
                'duration_minutes': form.cleaned_data.get('duration_minutes', 120) or 120,
            }

            request.session['recurring_event_form_data'] = form_data
            request.session['recurring_event_dates'] = date_list
            return redirect('event_add_recurring_preview', slug=slug)
    else:
        form = RecurringEventForm(initial={
            'voting_deadline_offset_minutes': SiteSettings.load().default_voting_offset_minutes,
        })

    return render(request, 'club/event_form_recurring.html', {
        'form': form,
        'voting_offset': SiteSettings.load().default_voting_offset_minutes,
        'group': group,
    })


def event_add_recurring_preview(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if not can_create_event(request.user, group):
        raise PermissionDenied

    form_data = request.session.get('recurring_event_dates')
    if not form_data:
        return redirect('event_add_recurring', slug=slug)

    dates_data = request.session.get('recurring_event_dates', [])
    event_data = request.session.get('recurring_event_form_data', {})

    dates = []
    for d in dates_data:
        dt = timezone.datetime.fromisoformat(d['datetime'])
        dates.append({
            'date': d['date'],
            'time': d['time'],
            'datetime': dt,
            'display': dt.strftime('%A, %B %d, %Y') + (f' at {dt.strftime("%I:%M %p")}' if dt.time() != dt_time(0, 0) else ''),
            'checked': d.get('checked', True),
        })

    if request.method == 'POST':
        if 'cancel' in request.POST:
            request.session.pop('recurring_event_form_data', None)
            request.session.pop('recurring_event_dates', None)
            return redirect('group_event_list', slug=slug)

        checked_indices = request.POST.getlist('selected_dates')
        checked_indices = [int(i) for i in checked_indices]

        if not checked_indices:
            return render(request, 'club/event_recurring_preview.html', {
                'dates': dates,
                'event_data': event_data,
                'error': 'You must select at least one date.',
            })

        offset = event_data.get('voting_deadline_offset_minutes', 0) or 0
        time_str = event_data.get('time', '')
        first_event = None

        for idx in checked_indices:
            d = dates_data[idx]
            dt = timezone.datetime.fromisoformat(d['datetime'])

            event = Event(
                title=event_data['title'],
                description=event_data.get('description', ''),
                location=event_data.get('location', ''),
                date=dt,
                created_by=request.user,
                group=group,
                voting_deadline_offset_minutes=offset,
                duration_minutes=event_data.get('duration_minutes', 120) or 120,
            )
            custom_vd_date = event_data.get('voting_deadline_date')
            custom_vd_time = event_data.get('voting_deadline_time')
            if custom_vd_date:
                vd_t = dt_time(0, 0)
                if custom_vd_time:
                    h, m = custom_vd_time.split(':')
                    vd_t = dt_time(int(h), int(m))
                vd_combined = datetime.combine(
                    datetime.strptime(custom_vd_date, '%Y-%m-%d').date(), vd_t
                )
                vd_combined = timezone.make_aware(vd_combined) if timezone.is_naive(vd_combined) else vd_combined
                event.voting_deadline = vd_combined
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.save()
            first_event = first_event if first_event else event

        if first_event:
            notify_group_event_created(
                group, first_event, request.user, count=len(checked_indices),
            )
            record_event_created_batch(
                first_event, request.user, count=len(checked_indices),
            )

        request.session.pop('recurring_event_form_data', None)
        request.session.pop('recurring_event_dates', None)
        return redirect('group_event_list', slug=slug)

    return render(request, 'club/event_recurring_preview.html', {
        'dates': dates,
        'event_data': event_data,
    })


def event_edit(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_organizer(request.user, event.group):
        raise PermissionDenied

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save(commit=False)
            if not event.is_ongoing:
                event.duration_minutes = form.cleaned_data.get('duration_minutes') or 120
            event.date = form.cleaned_data['date']
            offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0
            event.voting_deadline_offset_minutes = offset
            custom_deadline = form.cleaned_data.get('voting_deadline')
            if custom_deadline:
                event.voting_deadline = custom_deadline
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.save()
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            event.tags.set(tag_id_list)
            notify_group_event_updated(event.group, event, request.user)
            record_event_updated(event, request.user)
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
    else:
        form = EventForm(instance=event, initial={
            'voting_deadline_offset_minutes': event.voting_deadline_offset_minutes,
        })
    return render(request, 'club/event_form.html', {
        'form': form,
        'action': 'Edit',
        'voting_offset': event.voting_deadline_offset_minutes,
        'group': event.group,
        'initial_tags': list(event.tags.all()),
    })


def _validate_vote_submissions(post_data, games_qs):
    entries = []
    errors = []
    try:
        total_forms = int(post_data.get('form-TOTAL_FORMS', '0'))
    except (ValueError, TypeError):
        return [], ['Invalid form data.']
    if total_forms < 1:
        return [], ['You must vote for at least one game.']
    valid_game_ids = set(games_qs.values_list('pk', flat=True))
    seen_games = set()
    for i in range(total_forms):
        game_id_raw = post_data.get(f'form-{i}-board_game', '').strip()
        if not game_id_raw:
            ordinal = _rank_ordinal(i + 1)
            errors.append(f'{ordinal} choice: Please select a game.')
            continue
        try:
            game_id = int(game_id_raw)
        except (ValueError, TypeError):
            ordinal = _rank_ordinal(i + 1)
            errors.append(f'{ordinal} choice: Invalid game selection.')
            continue
        if game_id not in valid_game_ids:
            ordinal = _rank_ordinal(i + 1)
            errors.append(f'{ordinal} choice: Selected game is not available for this event.')
            continue
        if game_id in seen_games:
            ordinal = _rank_ordinal(i + 1)
            errors.append(f'{ordinal} choice: Duplicate game selection.')
            continue
        seen_games.add(game_id)
        entries.append((game_id, i + 1))
    return entries, errors


def _rank_ordinal(n):
    if 11 <= n <= 13:
        return f'{n}th'
    last = n % 10
    if last == 1:
        return f'{n}st'
    if last == 2:
        return f'{n}nd'
    if last == 3:
        return f'{n}rd'
    return f'{n}th'


def event_vote(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not can_view_group(request.user, event.group):
        raise PermissionDenied
    if not EventAttendance.objects.filter(user=request.user, event=event).exists():
        raise PermissionDenied

    event.sync_voting_status()
    event.refresh_from_db()

    games = event.group.games()
    game_count = games.count()

    existing_votes = Vote.objects.filter(
        user=request.user, event=event
    ).select_related('board_game').order_by('rank')
    vote_data = []
    for vote in existing_votes:
        vote_data.append({'board_game': vote.board_game_id, 'rank': vote.rank, 'game_name': vote.board_game.name})

    if not event.is_voting_open:
        if request.method == 'POST':
            return render(request, 'club/event_vote.html', {
                'event': event,
                'games': games,
                'game_count': game_count,
                'vote_data': vote_data,
                'voting_closed': True,
                'mid_submit_closed': True,
            })

        return render(request, 'club/event_vote.html', {
            'event': event,
            'games': games,
            'game_count': game_count,
            'vote_data': vote_data,
            'voting_closed': True,
            'mid_submit_closed': False,
        })

    if request.method == 'POST':
        entries, errors = _validate_vote_submissions(request.POST, games)
        if errors:
            return render(request, 'club/event_vote.html', {
                'event': event,
                'games': games,
                'game_count': game_count,
                'vote_data': vote_data,
                'voting_closed': False,
                'mid_submit_closed': False,
                'vote_errors': errors,
            })
        Vote.objects.filter(user=request.user, event=event).delete()
        for game_id, rank in entries:
            Vote.objects.create(
                user=request.user,
                event=event,
                board_game_id=game_id,
                rank=rank,
            )
        return redirect('event_detail', slug=event.group.slug, pk=event.pk)

    return render(request, 'club/event_vote.html', {
        'event': event,
        'games': games,
        'game_count': game_count,
        'voting_closed': False,
        'mid_submit_closed': False,
    })


def event_results(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_organizer(request.user, event.group):
        if not (request.user.is_superuser or request.user.is_site_admin):
            raise PermissionDenied
    scores = calculate_borda_scores(event)
    game_map = {g.pk: g for g in BoardGame.objects.filter(pk__in=scores.keys())}

    results = []
    for game_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        results.append({
            'game': game_map[game_id],
            'score': score,
        })

    show_individual = event.show_individual_votes
    individual_votes = None
    if show_individual:
        attendee_ids = EventAttendance.objects.filter(
            event=event
        ).values_list('user_id', flat=True)
        votes = Vote.objects.filter(
            event=event, user_id__in=attendee_ids
        ).select_related('user', 'board_game').order_by('user', 'rank')
        user_votes = {}
        for vote in votes:
            user_votes.setdefault(vote.user, []).append(vote)
        individual_votes = user_votes

    return render(request, 'club/event_results.html', {
        'event': event,
        'results': results,
        'show_individual': show_individual,
        'individual_votes': individual_votes,
    })


def event_toggle_visibility(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_admin(request.user, event.group):
        raise PermissionDenied
    event.show_individual_votes = not event.show_individual_votes
    event.save()
    return redirect('event_detail', slug=event.group.slug, pk=event.pk)


def event_toggle_voting(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_organizer(request.user, event.group):
        raise PermissionDenied
    event.sync_voting_status()
    event.refresh_from_db()

    if event.is_voting_open:
        event.voting_open = False
        event.save()
        notify_group_voting_ended(event.group, event, request.user)
    else:
        if not event.is_active:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        if timezone.now() >= event.voting_deadline:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        event.voting_open = True
        event.save()
        notify_group_voting_resumed(event.group, event, request.user)

    return redirect('event_detail', slug=event.group.slug, pk=event.pk)


def event_detail(request, slug, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied
    event = get_object_or_404(Event, pk=pk)
    if not can_view_group(request.user, event.group):
        raise PermissionDenied
    event.sync_voting_status()
    event.refresh_from_db()
    attendees = EventAttendance.objects.filter(event=event).select_related('user')
    is_attending = False
    if request.user.is_authenticated:
        is_attending = EventAttendance.objects.filter(
            user=request.user, event=event
        ).exists()
    can_resume = (
        not event.voting_open
        and event.is_currently_active
        and timezone.now() < event.voting_deadline
    )
    is_group_organizer_user = (
        request.user.is_authenticated
        and is_group_organizer(request.user, event.group)
    )
    game_sessions = GameSession.objects.filter(event=event).select_related('board_game').prefetch_related('players', 'players__user')
    return render(request, 'club/event_detail.html', {
        'event': event,
        'attendees': attendees,
        'is_attending': is_attending,
        'time_midnight': dt_time(0, 0),
        'can_resume': can_resume,
        'is_group_organizer': is_group_organizer_user,
        'game_sessions': game_sessions,
    })


def _rsvp_toggle(user, event):
    with transaction.atomic():
        attendance = EventAttendance.objects.select_for_update().filter(
            user=user, event=event,
        )
        if attendance.exists():
            attendance.delete()
        else:
            try:
                EventAttendance.objects.create(user=user, event=event)
            except IntegrityError:
                pass


def event_rsvp(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_member(request.user, event.group):
        raise PermissionDenied
    _rsvp_toggle(request.user, event)
    return redirect('event_detail', slug=event.group.slug, pk=event.pk)


def _admin_required(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not (request.user.is_superuser or request.user.is_site_admin):
        raise PermissionDenied
    return None


@site_admin_required
def admin_settings(request):
    site_settings = SiteSettings.load()
    current_total = site_settings.default_voting_offset_minutes
    offset_hours = current_total // 60
    offset_mins = current_total % 60

    if request.method == 'POST':
        if request.user.is_superuser and 'site_lockdown_active' in request.POST:
            site_settings.site_lockdown_active = True
            site_settings.site_lockdown_allow_site_admins = (
                'site_lockdown_allow_site_admins' in request.POST
            )
            site_settings.save()
            return redirect('admin_settings')

        if request.user.is_superuser and 'site_lockdown_deactivate' in request.POST:
            site_settings.site_lockdown_active = False
            site_settings.site_lockdown_allow_site_admins = False
            site_settings.save()
            return redirect('admin_settings')

        offset_hours = request.POST.get('default_voting_offset_hours', '0')
        offset_mins_val = request.POST.get('default_voting_offset_minutes_field', '0')
        try:
            total_minutes = int(offset_hours) * 60 + int(offset_mins_val)
        except (ValueError, TypeError):
            total_minutes = 0
        if site_settings.default_voting_offset_minutes != total_minutes:
            site_settings.default_voting_offset_minutes = total_minutes
            site_settings.save()

        duration_val = request.POST.get('default_event_duration_minutes', '120')
        try:
            duration_minutes = int(duration_val)
            if duration_minutes < 1:
                duration_minutes = 120
        except (ValueError, TypeError):
            duration_minutes = 120
        if site_settings.default_event_duration_minutes != duration_minutes:
            site_settings.default_event_duration_minutes = duration_minutes
            site_settings.save()

        co_creators_val = request.POST.get('max_co_creators', '3')
        try:
            max_co = int(co_creators_val)
            if max_co < 0:
                max_co = 3
        except (ValueError, TypeError):
            max_co = 3
        if site_settings.max_co_creators != max_co:
            site_settings.max_co_creators = max_co
            site_settings.save()
        return redirect('admin_settings')

    site_admins = User.objects.filter(
        Q(is_site_admin=True) | Q(is_superuser=True),
    ).order_by('username')

    return render(request, 'club/site_admin_settings.html', {
        'verified_icons': VerifiedIcon.objects.all().order_by('name'),
        'icon_manage_form': VerifiedIconForm(),
        'site_settings': site_settings,
        'offset_hour_choices': list(range(0, 25)),
        'offset_minute_choices': list(range(0, 60, 5)),
        'current_offset_hours': offset_hours,
        'current_offset_minutes': offset_mins,
        'site_admins': site_admins,
    })


def _superuser_required(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.is_superuser:
        raise PermissionDenied
    return None


def manage_site_admins(request):
    redirect_resp = _superuser_required(request)
    if redirect_resp:
        return redirect_resp

    if request.method == 'POST':
        add_ids = request.POST.getlist('add')
        remove_ids = request.POST.getlist('remove')
        add_set = set(add_ids) - set(remove_ids)
        remove_set = set(remove_ids) - set(add_ids)

        for uid in add_set:
            try:
                user = User.objects.get(pk=int(uid))
                if not user.is_superuser:
                    user.is_site_admin = True
                    user.save(update_fields=['is_site_admin'])
            except (User.DoesNotExist, ValueError, TypeError):
                pass

        for uid in remove_set:
            try:
                user = User.objects.get(pk=int(uid))
                if not user.is_superuser:
                    user.is_site_admin = False
                    user.save(update_fields=['is_site_admin'])
            except (User.DoesNotExist, ValueError, TypeError):
                pass

        return redirect('manage_site_admins')

    current_admins = User.objects.filter(is_site_admin=True).order_by('username')
    return render(request, 'club/manage_site_admins.html', {
        'current_admins': current_admins,
    })


def manage_site_admins_search(request):
    redirect_resp = _superuser_required(request)
    if redirect_resp:
        return redirect_resp

    query = request.GET.get('q', '').strip()
    results = []
    if query:
        qs = User.objects.exclude(is_superuser=True).exclude(is_site_admin=True)
        if query.isdigit():
            qs = qs.filter(pk=int(query))
        else:
            qs = qs.filter(username__icontains=query)
        results = list(qs[:10].values('id', 'username'))

    return JsonResponse({'results': results})


def add_verified_icon(request):
    redirect_resp = _admin_required(request)
    if redirect_resp:
        return redirect_resp
    if request.method == 'POST':
        form = VerifiedIconForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('admin_settings')
        return render(request, 'club/site_admin_settings.html', {
            'verified_icons': VerifiedIcon.objects.all().order_by('name'),
            'icon_manage_form': form,
            'icon_add_error': True,
        })
    return redirect('admin_settings')


def delete_verified_icon(request, pk):
    redirect_resp = _admin_required(request)
    if redirect_resp:
        return redirect_resp
    icon = get_object_or_404(VerifiedIcon, pk=pk)
    if request.method == 'POST':
        user_count = User.objects.filter(verified_icon=icon).count()
        if user_count > 0:
            return render(request, 'club/site_admin_settings.html', {
                'verified_icons': VerifiedIcon.objects.all().order_by('name'),
                'icon_delete_error': f'Cannot delete "{icon.name}" — {user_count} user{"s" if user_count != 1 else ""} {"are" if user_count != 1 else "is"} using this icon.',
                'icon_manage_form': VerifiedIconForm(),
            })
        icon.delete()
    return redirect('admin_settings')


def notification_list(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    notifications = Notification.objects.filter(user=request.user)

    blocked_ids = Block.get_blocked_user_ids(request.user)
    if blocked_ids:
        blocked_usernames = set(
            User.objects.filter(pk__in=blocked_ids).values_list('username', flat=True)
        )
        direct_types = {
            'friend_request', 'friend_request_accepted', 'friend_request_declined',
            'event_invite', 'event_invite_accepted', 'event_invite_declined',
            'event_organizer_designated',
        }
        filtered_ids = []
        for n in notifications:
            if n.notification_type not in direct_types:
                continue
            parts = (n.url or '').strip('/').split('/')
            username = parts[-1] if parts else ''
            if username in blocked_usernames:
                filtered_ids.append(n.pk)
        if filtered_ids:
            notifications = notifications.exclude(pk__in=filtered_ids)

    friendship_pks = {}
    friend_notifs = notifications.filter(
        notification_type='friend_request', is_read=False,
    )
    for n in friend_notifs:
        parts = n.url.strip('/').split('/')
        username = parts[-1] if parts else ''
        if not username:
            continue
        requester = User.objects.filter(username__iexact=username).first()
        if not requester:
            continue
        friendship = Friendship.objects.filter(
            requester=requester,
            receiver=request.user,
            status='pending',
        ).first()
        if friendship:
            friendship_pks[n.pk] = friendship.pk

    return render(request, 'club/notification_list.html', {
        'notifications': notifications,
        'friendship_pks': friendship_pks,
    })


def notification_mark_read(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'read'})
    if notif.url and url_has_allowed_host_and_scheme(
        notif.url, allowed_hosts=settings.ALLOWED_HOSTS, require_https=True
    ):
        return redirect(notif.url)
    return redirect('notification_list')


def notification_mark_all_read(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notification_list')


def notification_delete_selected(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    selected = request.POST.getlist('selected_notifications')
    if selected:
        Notification.objects.filter(
            pk__in=selected,
            user=request.user,
            is_read=True,
        ).delete()
    return redirect('notification_list')


@login_required
def group_list(request):
    tab = request.GET.get('tab', 'my')
    query = request.GET.get('q', '')

    memberships = GroupMembership.objects.filter(
        user=request.user,
    ).select_related('group').order_by('-is_favorite', 'group__name')

    my_groups = [m.group for m in memberships]
    member_group_ids = {m.group_id for m in memberships}
    favorite_group_ids = {m.group_id for m in memberships if m.is_favorite}
    admin_group_ids = {m.group_id for m in memberships if m.role == 'admin'}

    if tab == 'my':
        groups = my_groups
    elif tab == 'all':
        groups = list(Group.objects.filter(
            Q(discoverable=True) | Q(membership__user=request.user),
        ).filter(
            disbanded_at__isnull=True,
        ).distinct().order_by('name'))
    elif tab == 'pending':
        groups = []
    else:
        groups = my_groups

    if query:
        from django.utils.text import slugify
        q_lower = query.lower()
        groups = [g for g in groups if q_lower in g.name.lower()]

    pending_requests = GroupJoinRequest.objects.filter(
        user=request.user,
        status='pending',
        expires_at__gt=timezone.now(),
    ).select_related('group') if tab == 'pending' else []

    return render(request, 'club/group_list.html', {
        'groups': groups,
        'tab': tab,
        'query': query,
        'my_groups': my_groups,
        'pending_requests': pending_requests,
        'member_group_ids': member_group_ids,
        'favorite_group_ids': favorite_group_ids,
        'admin_group_ids': admin_group_ids,
    })


@login_required
def group_create(request):
    if not can_create_group(request.user):
        from django.contrib import messages
        messages.error(request, 'You have reached your group creation limit. Contact a site admin for more.')
        return redirect('group_list')
    if request.method == 'POST':
        form = GroupCreateForm(request.POST, request.FILES)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            if group.image:
                buffer = resize_group_image(group.image)
                group.image.save(
                    group.image.name,
                    buffer,
                    save=False,
                )
            group.save()
            GroupMembership.objects.create(
                user=request.user,
                group=group,
                role='admin',
            )
            GroupCreationLog.objects.create(
                user=request.user,
                group=group,
            )
            return redirect('group_dashboard', slug=group.slug)
    else:
        form = GroupCreateForm()
    return render(request, 'club/group_create.html', {'form': form})


def group_dashboard(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not can_view_group(request.user, group):
        raise PermissionDenied

    is_member = group.is_member(request.user) if request.user.is_authenticated else False
    is_admin_user = group.is_admin(request.user) if request.user.is_authenticated else False
    is_organizer_user = (
        request.user.is_authenticated
        and is_group_organizer(request.user, group)
    )

    members = (
        GroupMembership.objects.filter(
            group=group,
        ).select_related('user', 'user__verified_icon').order_by('-role', 'joined_at')
        if request.user.is_authenticated
        else GroupMembership.objects.none()
    )

    upcoming_events = (
        Event.objects.filter(
            group=group,
            end_time__gte=timezone.now(),
        ).order_by('date')[:5]
        if request.user.is_authenticated
        else Event.objects.none()
    )

    return render(request, 'club/group_dashboard.html', {
        'group': group,
        'is_member': is_member,
        'is_admin': is_admin_user,
        'is_organizer': is_organizer_user,
        'members': members,
        'upcoming_events': upcoming_events,
    })


@login_required
def group_settings(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not can_edit_group_settings(request.user, group):
        raise PermissionDenied
    if group.is_disbanded:
        raise PermissionDenied

    if request.method == 'POST':
        form = GroupSettingsForm(request.POST, request.FILES, instance=group, user=request.user)
        if form.is_valid():
            if not request.user.is_superuser:
                original_max = Group.objects.get(pk=group.pk).max_members
            group = form.save(commit=False)
            if not request.user.is_superuser:
                group.max_members = original_max
            if 'image' in request.FILES:
                buffer = resize_group_image(request.FILES['image'])
                group.image.save(
                    request.FILES['image'].name,
                    buffer,
                    save=False,
                )
            group.save()
            notify_group_settings_changed(group, request.user)
            return redirect('group_dashboard', slug=group.slug)
    else:
        form = GroupSettingsForm(instance=group, user=request.user)
    return render(request, 'club/group_settings.html', {'form': form, 'group': group})


@login_required
def group_favorite(request, slug):
    group = get_object_or_404(Group, slug=slug)
    membership = get_object_or_404(GroupMembership, user=request.user, group=group)
    if request.method == 'POST':
        membership.is_favorite = not membership.is_favorite
        membership.save(update_fields=['is_favorite'])
    return redirect('group_list')


def group_delete(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/?next=' + request.path)
    if not can_delete_group(request.user):
        raise PermissionDenied

    group = get_object_or_404(Group, slug=slug)

    if request.method == 'POST':
        typed_name = request.POST.get('confirm_name', '')
        if typed_name == group.name:
            group.delete()
            return redirect('group_list')
        return render(request, 'club/group_delete_confirm.html', {
            'group': group,
            'error': 'Group name does not match.',
        })

    return render(request, 'club/group_delete_confirm.html', {'group': group})


def group_restore(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/?next=' + request.path)
    if not can_restore_group(request.user):
        raise PermissionDenied

    group = get_object_or_404(Group, slug=slug)

    if not group.is_disbanded:
        return redirect('group_dashboard', slug=group.slug)

    if request.method == 'POST':
        group.disbanded_at = None
        group.save(update_fields=['disbanded_at'])
        if not GroupMembership.objects.filter(group=group).exists():
            GroupMembership.objects.create(
                user=request.user,
                group=group,
                role='admin',
            )
        notify_group_restored(group, request.user)
        return redirect('group_dashboard', slug=group.slug)

    return render(request, 'club/group_restore_confirm.html', {'group': group})


def group_members(request, slug):
    if not request.user.is_authenticated:
        raise PermissionDenied
    group = get_object_or_404(Group, slug=slug)
    if not can_view_group(request.user, group):
        raise PermissionDenied

    members = GroupMembership.objects.filter(
        group=group,
    ).select_related('user', 'user__verified_icon').order_by(
        '-role', 'joined_at',
    )

    is_admin_user = group.is_admin(request.user) if request.user.is_authenticated else False

    return render(request, 'club/group_members.html', {
        'group': group,
        'members': members,
        'is_admin': is_admin_user,
    })


@login_required
def group_members_manage(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not is_group_admin(request.user, group):
        raise PermissionDenied

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        membership = GroupMembership.objects.filter(
            user_id=user_id, group=group,
        ).first()

        if membership and membership.user != request.user:
            requires_confirm = (
                membership.role == 'admin'
                and action in ('remove', 'demote_organizer', 'demote_member')
                and not request.POST.get('confirmed')
            )
            if requires_confirm:
                action_labels = {
                    'remove': 'remove',
                    'demote_organizer': 'demote to organizer',
                    'demote_member': 'demote to member',
                }
                return render(request, 'club/group_admin_action_confirm.html', {
                    'group': group,
                    'target_membership': membership,
                    'action': action,
                    'action_label': action_labels[action],
                })
            if action == 'promote_organizer':
                membership.role = 'organizer'
                membership.save(update_fields=['role'])
                notify_group_promoted_organizer(membership.user, group, request.user)
            elif action == 'promote_admin':
                membership.role = 'admin'
                membership.save(update_fields=['role'])
                notify_group_promoted_admin(membership.user, group, request.user)
            elif action == 'demote_member':
                membership.role = 'member'
                membership.save(update_fields=['role'])
                notify_group_demoted_member(membership.user, group, request.user)
            elif action == 'demote_organizer':
                membership.role = 'organizer'
                membership.save(update_fields=['role'])
                notify_group_demoted_organizer(membership.user, group, request.user)
            elif action == 'remove':
                notify_group_removed(membership.user, group, request.user)
                _clean_remove_member(membership.user, group)
                membership.delete()
                if group.membership.count() == 0:
                    group.disbanded_at = timezone.now()
                    group.save(update_fields=['disbanded_at'])
                    notify_group_grace_period(group)

    members = GroupMembership.objects.filter(
        group=group,
    ).select_related('user', 'user__verified_icon').order_by(
        '-role', 'joined_at',
    )

    return render(request, 'club/group_members_manage.html', {
        'group': group,
        'members': members,
    })


@login_required
def group_join(request, slug):
    group = get_object_or_404(Group, slug=slug)

    if group.is_disbanded:
        return render(request, 'club/group_join.html', {
            'group': group,
            'error': 'This group has been disbanded.',
        })

    if group.is_member(request.user):
        return redirect('group_dashboard', slug=group.slug)

    if group.membership.count() >= group.max_members:
        return render(request, 'club/group_join.html', {
            'group': group,
            'error': 'This group is full.',
        })

    if request.method == 'POST':
        if group.join_policy == 'open':
            with transaction.atomic():
                locked_group = Group.objects.select_for_update().get(pk=group.pk)
                if locked_group.membership.count() >= locked_group.max_members:
                    return render(request, 'club/group_join.html', {
                        'group': group,
                        'error': 'This group is full.',
                    })
                GroupMembership.objects.create(
                    user=request.user,
                    group=group,
                    role='member',
                )
            notify_group_member_joined(group, request.user, method='open join')
            record_member_joined(request.user, group)
            return redirect('group_dashboard', slug=group.slug)
        elif group.join_policy == 'request':
            with transaction.atomic():
                locked_group = Group.objects.select_for_update().get(pk=group.pk)
                if locked_group.membership.count() >= locked_group.max_members:
                    return render(request, 'club/group_join.html', {
                        'group': group,
                        'error': 'This group is full.',
                    })
                if not GroupJoinRequest.objects.filter(
                    user=request.user, group=group, status='pending',
                ).exists():
                    GroupJoinRequest.objects.create(
                        user=request.user,
                        group=group,
                        expires_at=timezone.now() + __import__('datetime').timedelta(days=7),
                    )
                    notify_group_join_request(group, request.user)
            return render(request, 'club/group_join.html', {
                'group': group,
                'message': 'Your join request has been submitted.',
            })
        else:
            raise PermissionDenied

    return render(request, 'club/group_join.html', {'group': group})


@login_required
def group_leave(request, slug):
    group = get_object_or_404(Group, slug=slug)
    membership = get_object_or_404(
        GroupMembership, user=request.user, group=group,
    )

    if membership.role == 'admin':
        other_admins = GroupMembership.objects.filter(
            group=group, role='admin',
        ).exclude(user=request.user).exists()

        if not other_admins:
            other_members = GroupMembership.objects.filter(
                group=group,
            ).exclude(user=request.user)
            if other_members.exists():
                if request.method == 'POST':
                    form = SuccessorPickForm(
                        request.POST, members=other_members,
                    )
                    if form.is_valid():
                        successor_id = form.cleaned_data['successor']
                        GroupMembership.objects.filter(
                            user_id=successor_id, group=group,
                        ).update(role='admin')
                        notify_group_member_left(group, request.user)
                        _clean_remove_member(request.user, group)
                        membership.delete()
                        return redirect('group_list')
                else:
                    form = SuccessorPickForm(members=other_members)
                return render(request, 'club/group_leave_confirm.html', {
                    'group': group,
                    'form': form,
                    'members': other_members,
                    'needs_successor': True,
                })

    if request.method == 'POST':
        notify_group_member_left(group, request.user)
        _clean_remove_member(request.user, group)
        membership.delete()
        if group.membership.count() == 0:
            group.disbanded_at = timezone.now()
            group.save(update_fields=['disbanded_at'])
            notify_group_grace_period(group)
        return redirect('group_list')

    remaining = GroupMembership.objects.filter(group=group).count()
    return render(request, 'club/group_leave_confirm.html', {
        'group': group,
        'needs_successor': False,
        'is_last_member': remaining == 1,
    })


@login_required
def group_join_request_manage(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not is_group_admin(request.user, group):
        raise PermissionDenied

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        join_request = GroupJoinRequest.objects.filter(
            pk=request_id, group=group, status='pending',
        ).first()

        if join_request:
            try:
                if action == 'approve':
                    join_request.approve()
                    notify_group_join_approved(join_request.user, group, request.user)
                    notify_group_member_joined(group, join_request.user, method='join request')
                    record_member_joined(join_request.user, group)
                elif action == 'reject':
                    join_request.reject()
                    notify_group_join_rejected(join_request.user, group, request.user)
            except ValueError:
                pass

    requests = GroupJoinRequest.objects.filter(
        group=group, status='pending', expires_at__gt=timezone.now(),
    ).select_related('user').order_by('-created_at')

    return render(request, 'club/group_join_request_manage.html', {
        'group': group,
        'requests': requests,
    })


def _clean_remove_member(user, group):
    from .models import EventAttendance
    upcoming_events = Event.objects.filter(
        group=group,
        end_time__gte=timezone.now(),
    )
    EventAttendance.objects.filter(
        user=user,
        event__in=upcoming_events,
    ).delete()
    Vote.objects.filter(
        user=user,
        event__in=upcoming_events,
    ).delete()


@login_required
def group_invite_create(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not is_group_admin(request.user, group):
        raise PermissionDenied

    if group.is_disbanded:
        raise PermissionDenied

    invite = None
    if request.method == 'POST':
        invite = GroupInvite.objects.create(
            group=group,
            created_by=request.user,
            expires_at=timezone.now() + __import__('datetime').timedelta(days=7),
        )
        notify_group_invite_created(group, request.user)

    return render(request, 'club/group_invite.html', {
        'group': group,
        'invite': invite,
    })


def group_invite_accept(request, token):
    invite = GroupInvite.objects.filter(token=token).first()

    if not invite:
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This invite link is invalid.',
        })

    if invite.used:
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This invite has already been used.',
        })

    if not invite.is_valid():
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This invite has expired.',
        })

    if invite.group.is_disbanded:
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This group has been disbanded.',
        })

    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/invite/{token}/')

    try:
        invite.use(request.user)
        notify_group_member_joined(invite.group, request.user, method='invite')
        record_member_joined(request.user, invite.group)
        return redirect('group_dashboard', slug=invite.group.slug)
    except ValueError as e:
        return render(request, 'club/group_invite_accept.html', {
            'error': str(e),
        })


# ---------------------------------------------------------------------------
# Block views
# ---------------------------------------------------------------------------

@login_required
def block_user(request, username):
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    target = get_object_or_404(User, username__iexact=username)
    if target == request.user:
        raise PermissionDenied

    Block.objects.get_or_create(blocker=request.user, blocked=target)

    Friendship.objects.filter(
        Q(requester=request.user, receiver=target)
        | Q(requester=target, receiver=request.user),
    ).delete()

    Notification.objects.filter(
        user=request.user,
        notification_type='friend_request',
        url=f'/profile/{target.username}/',
    ).delete()
    Notification.objects.filter(
        user=target,
        notification_type='friend_request',
        url=f'/profile/{request.user.username}/',
    ).delete()

    return redirect('public_profile', username=username)


@login_required
def unblock_user(request, username):
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    target = get_object_or_404(User, username__iexact=username)
    Block.objects.filter(blocker=request.user, blocked=target).delete()
    return redirect('public_profile', username=username)


# ---------------------------------------------------------------------------
# Friendship views
# ---------------------------------------------------------------------------

@login_required
def send_friend_request(request, username):
    target = get_object_or_404(User, username__iexact=username)
    if target == request.user:
        raise PermissionDenied
    if Block.is_blocked(request.user, target):
        raise PermissionDenied
    if not Friendship.can_send_request(request.user, target):
        from django.contrib import messages
        messages.warning(request, 'You cannot send a friend request right now.')
        return redirect('public_profile', username=username)

    existing = Friendship.objects.filter(
        requester=request.user, receiver=target,
    ).first()
    if existing and existing.status == 'declined':
        existing.status = 'pending'
        existing.save(update_fields=['status', 'updated_at'])
    elif not existing:
        Friendship.objects.create(requester=request.user, receiver=target)

    from .notifications import notify_friend_request_sent
    notify_friend_request_sent(target, request.user)
    from django.contrib import messages
    messages.success(request, f'Friend request sent to {username}')
    return redirect('public_profile', username=username)


@login_required
def accept_friend_request(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk)
    if friendship.receiver != request.user:
        raise PermissionDenied
    if friendship.status != 'pending':
        raise PermissionDenied
    if Block.is_blocked(request.user, friendship.requester):
        raise PermissionDenied

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        friendship.status = 'accepted'
        friendship.save(update_fields=['status', 'updated_at'])
        from .notifications import notify_friend_request_accepted
        notify_friend_request_accepted(friendship.requester, request.user)

        if is_ajax:
            Notification.objects.filter(
                user=request.user,
                notification_type='friend_request',
                url=f'/profile/{friendship.requester.username}/',
                is_read=False,
            ).update(is_read=True)
            return JsonResponse({
                'status': 'accepted',
                'username': friendship.requester.username,
            })

        return redirect('public_profile', username=friendship.requester.username)

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    return redirect('public_profile', username=friendship.requester.username)


@login_required
def decline_friend_request(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk)
    if friendship.receiver != request.user:
        raise PermissionDenied
    if friendship.status != 'pending':
        raise PermissionDenied
    if Block.is_blocked(request.user, friendship.requester):
        raise PermissionDenied

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        friendship.status = 'declined'
        friendship.decline_count += 1
        friendship.last_declined_at = timezone.now()
        friendship.save(update_fields=['status', 'decline_count', 'last_declined_at', 'updated_at'])
        from .notifications import notify_friend_request_declined
        notify_friend_request_declined(friendship.requester, request.user)

        if is_ajax:
            Notification.objects.filter(
                user=request.user,
                notification_type='friend_request',
                url=f'/profile/{friendship.requester.username}/',
                is_read=False,
            ).update(is_read=True)
            return JsonResponse({
                'status': 'declined',
                'username': friendship.requester.username,
            })

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    return redirect('notification_list')


def _is_event_organizer(user, event):
    if event.group_id is not None:
        return is_group_organizer(user, event.group)
    return event.is_organizer(user)


@login_required
def event_toggle_presence(request, pk):
    from django.http import HttpResponseNotAllowed, JsonResponse
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    event = get_object_or_404(Event, pk=pk)

    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin

    if not is_org and not is_privileged:
        raise PermissionDenied

    from .presence import is_presence_locked
    locked, _ = is_presence_locked(event)
    if locked and not is_privileged:
        raise PermissionDenied

    import json
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    user_id = body.get('user_id') or request.POST.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'invalid user_id'}, status=400)

    target_user = User.objects.filter(pk=user_id).first()
    if not target_user:
        return JsonResponse({'error': 'user not found'}, status=400)

    if event.group_id is not None:
        if not EventAttendance.objects.filter(user=target_user, event=event).exists():
            return JsonResponse({'error': 'user is not an attendee'}, status=400)
    else:
        if not can_view_private_event(target_user, event):
            return JsonResponse({'error': 'user does not have access to this event'}, status=400)

    from .models import EventPresence
    presence = EventPresence.objects.filter(event=event, user=target_user).first()
    if presence:
        presence.delete()
        return JsonResponse({'present': False, 'user_id': target_user.pk})
    else:
        EventPresence.objects.create(
            event=event, user=target_user, marked_by=request.user
        )
        return JsonResponse({'present': True, 'user_id': target_user.pk})


@login_required
def event_game_pool(request, pk):
    from django.http import HttpResponseNotAllowed
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    event = get_object_or_404(Event, pk=pk)

    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    from .game_pool import compute_game_pool
    pool = compute_game_pool(event)

    from .presence import is_presence_locked
    locked, lock_time = is_presence_locked(event)

    present_user_ids = set(
        EventPresence.objects.filter(event=event).values_list('user_id', flat=True)
    )

    if event.group_id is not None:
        attendees = EventAttendance.objects.filter(
            event=event
        ).select_related('user')
    else:
        from .permissions import can_view_private_event
        all_users = User.objects.all()
        attendees = [u for u in all_users if can_view_private_event(u, event)]

    pool_list = sorted(pool.values(), key=lambda x: x['name'])

    return render(request, 'club/event_game_pool.html', {
        'event': event,
        'pool': pool_list,
        'attendees': attendees if event.group_id is not None else [],
        'accessible_users': attendees if event.group_id is None else [],
        'present_user_ids': present_user_ids,
        'locked': locked,
        'lock_time': lock_time,
    })


@login_required
def event_pool_override(request, pk):
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    event = get_object_or_404(Event, pk=pk)
    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    import json
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    board_game_id = body.get('board_game_id') or request.POST.get('board_game_id')
    is_available_str = body.get('is_available', '')
    if not board_game_id:
        return JsonResponse({'error': 'board_game_id required'}, status=400)
    try:
        board_game_id = int(board_game_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'invalid board_game_id'}, status=400)

    game = BoardGame.objects.filter(pk=board_game_id).first()
    if not game:
        return JsonResponse({'error': 'game not found'}, status=400)

    if str(is_available_str).lower() == 'true':
        EventGameOverride.objects.update_or_create(
            event=event, board_game=game,
            defaults={'is_available': True, 'modified_by': request.user},
        )
    else:
        EventGameOverride.objects.filter(
            event=event, board_game=game
        ).delete()

    return JsonResponse({'game_id': game.pk, 'available': str(is_available_str).lower() == 'true'})


@login_required
def event_random_select(request, pk):
    from django.http import HttpResponseNotAllowed
    import random
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    event = get_object_or_404(Event, pk=pk)
    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    from .game_pool import compute_game_pool
    pool = compute_game_pool(event)
    available = [entry for entry in pool.values() if entry['is_available']]
    if not available:
        return JsonResponse({'error': 'No available games in pool'})

    choice = random.choice(available)
    return JsonResponse({
        'name': choice['name'],
        'bgg_id': choice['bgg_id'],
        'owners': choice['owners'],
        'min_players': choice['min_players'],
        'max_players': choice['max_players'],
        'complexity': choice['complexity'],
    })


@login_required
def event_play_game(request, pk):
    event = get_object_or_404(Event, pk=pk)
    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    if not event.is_currently_active:
        from django.contrib import messages
        messages.error(request, 'Cannot record games for an event that has ended.')
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    if request.method == 'POST':
        board_game_id = request.POST.get('board_game', '').strip()
        ad_hoc_name = request.POST.get('ad_hoc_game_name', '').strip()
        if board_game_id:
            board_game = get_object_or_404(BoardGame, pk=board_game_id)
        elif ad_hoc_name:
            board_game = BoardGame.objects.create(
                name=ad_hoc_name, is_temporary=True,
            )
        else:
            from django.contrib import messages
            messages.error(request, 'Select a game or enter a new game name.')
            if event.group_id is not None:
                return redirect('event_play_game', pk=event.pk)
            return redirect('event_play_game', pk=event.pk)
        selection_method = request.POST.get('selection_method', 'manual')
        session = GameSession.objects.create(
            event=event,
            board_game=board_game,
            selection_method=selection_method,
            created_by=request.user,
        )
        player_ids = request.POST.getlist('players')
        if not player_ids:
            raw = request.POST.get('players', '')
            if raw:
                player_ids = [p.strip() for p in raw.split(',') if p.strip()]
        for uid in player_ids:
            try:
                user_obj = User.objects.get(pk=int(uid))
            except (User.DoesNotExist, ValueError):
                continue
            GameSessionPlayer.objects.create(
                game_session=session, user=user_obj,
            )
        guest_names = request.POST.get('guest_names', '')
        if guest_names:
            for name in guest_names.split(','):
                name = name.strip()
                if name:
                    GameSessionPlayer.objects.create(
                        game_session=session, guest_name=name,
                    )
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    from .game_pool import compute_game_pool
    pool = compute_game_pool(event)
    games = list(pool.values())
    attendees = EventAttendance.objects.filter(event=event).select_related('user')
    preselected_game = request.GET.get('game', '')
    preselected_method = request.GET.get('method', 'manual')
    context = {
        'event': event,
        'games': games,
        'attendees': attendees,
        'preselected_game': preselected_game,
        'preselected_method': preselected_method,
    }
    return render(request, 'club/event_play_game.html', context)


@login_required
def game_session_detail(request, event_pk, pk):
    event = get_object_or_404(Event, pk=event_pk)
    session = get_object_or_404(GameSession, pk=pk, event=event)
    if event.group_id is not None:
        if not can_view_group(request.user, event.group):
            raise PermissionDenied
    else:
        if not can_view_private_event(request.user, event):
            raise PermissionDenied
    players = session.players.all()
    context = {
        'event': event,
        'session': session,
        'players': players,
    }
    return render(request, 'club/game_session_detail.html', context)


@login_required
def game_session_delete(request, event_pk, pk):
    event = get_object_or_404(Event, pk=event_pk)
    session = get_object_or_404(GameSession, pk=pk, event=event)
    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    if request.method == 'POST':
        session.delete()
        return redirect('private_event_detail', pk=event.pk)

    context = {
        'event': event,
        'session': session,
    }
    return render(request, 'club/game_session_confirm_delete.html', context)


@login_required
def event_extend(request, pk):
    event = get_object_or_404(Event, pk=pk)
    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    if not event.is_ongoing:
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    if request.method == 'POST':
        try:
            additional = int(request.POST.get('additional_minutes', 0))
        except (ValueError, TypeError):
            additional = 0
        if additional < 1:
            if event.group_id is not None:
                return redirect('event_detail', slug=event.group.slug, pk=event.pk)
            return redirect('private_event_detail', pk=event.pk)
        event.duration_minutes += additional
        event.end_time = event.end_time + timezone.timedelta(minutes=additional)
        event.save(update_fields=['duration_minutes', 'end_time'])
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    if event.group_id is not None:
        return redirect('event_detail', slug=event.group.slug, pk=event.pk)
    return redirect('private_event_detail', pk=event.pk)


@login_required
def event_end_early(request, pk):
    event = get_object_or_404(Event, pk=pk)
    is_org = _is_event_organizer(request.user, event)
    is_privileged = request.user.is_superuser or request.user.is_site_admin
    if not is_org and not is_privileged:
        raise PermissionDenied

    if not event.is_ongoing:
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    if request.method == 'POST':
        now = timezone.now()
        event.ended_early_at = now
        event.end_time = now
        event.save(update_fields=['ended_early_at', 'end_time'])
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    if event.group_id is not None:
        return redirect('event_detail', slug=event.group.slug, pk=event.pk)
    return redirect('private_event_detail', pk=event.pk)


@login_required
def event_timer_status(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.group_id is not None:
        if not can_view_group(request.user, event.group):
            raise PermissionDenied
    else:
        if not can_view_private_event(request.user, event):
            raise PermissionDenied
    from django.http import JsonResponse
    data = {
        'end_time': event.end_time.isoformat() if event.end_time else None,
        'ended_early_at': event.ended_early_at.isoformat() if event.ended_early_at else None,
        'is_active': event.is_currently_active,
    }
    return JsonResponse(data)


@login_required
def cancel_friend_request(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk)
    if friendship.requester != request.user:
        raise PermissionDenied
    if friendship.status != 'pending':
        raise PermissionDenied
    if Block.is_blocked(request.user, friendship.receiver):
        raise PermissionDenied

    if request.method == 'POST':
        target_username = friendship.receiver.username
        Notification.objects.filter(
            user=friendship.receiver,
            notification_type='friend_request',
            url=f'/profile/{request.user.username}/',
        ).delete()
        friendship.delete()
        return redirect('public_profile', username=target_username)

    return redirect('public_profile', username=friendship.receiver.username)


@login_required
def remove_friend(request, username):
    target = get_object_or_404(User, username__iexact=username)
    friendship = Friendship.objects.filter(
        status='accepted',
    ).filter(
        Q(requester=request.user, receiver=target)
        | Q(requester=target, receiver=request.user),
    ).first()
    if not friendship:
        raise PermissionDenied

    if request.method == 'POST':
        friendship.delete()
    return redirect('public_profile', username=username)


@login_required
def users_page(request):
    tab = request.GET.get('tab', 'friends')
    if tab not in ('friends', 'all'):
        tab = 'friends'

    context = {
        'tab': tab,
    }

    if tab == 'friends':
        friends = Friendship.get_friends_of(request.user)
        blocked_ids = Block.get_blocked_user_ids(request.user)
        friends = friends.exclude(pk__in=blocked_ids)

        user_group_ids = set(
            GroupMembership.objects.filter(user=request.user).values_list('group_id', flat=True)
        )

        friends_mutual_groups = {}
        for friend in friends:
            mutual = GroupMembership.objects.filter(
                user=friend, group_id__in=user_group_ids,
            ).select_related('group')
            friends_mutual_groups[friend.pk] = list(mutual)

        user_event_ids = set(
            EventAttendance.objects.filter(user=request.user).values_list('event_id', flat=True)
        )
        upcoming_private_event_ids = Event.objects.filter(
            pk__in=user_event_ids,
            group__isnull=True,
            end_time__gt=timezone.now(),
        ).values_list('pk', flat=True)

        friends_shared_events = {}
        for friend in friends:
            shared = EventAttendance.objects.filter(
                user=friend, event_id__in=upcoming_private_event_ids,
            ).select_related('event')
            friends_shared_events[friend.pk] = list(shared)

        pending_received = Friendship.objects.filter(
            receiver=request.user, status='pending',
        ).select_related('requester')

        pending_mutual_groups = {}
        for pr in pending_received:
            mutual = GroupMembership.objects.filter(
                user=pr.requester, group_id__in=user_group_ids,
            ).select_related('group')
            pending_mutual_groups[pr.pk] = list(mutual)

        sent_requests = Friendship.objects.filter(
            requester=request.user, status='pending',
        ).select_related('receiver')

        context.update({
            'friends': friends,
            'friends_mutual_groups': friends_mutual_groups,
            'friends_shared_events': friends_shared_events,
            'pending_received': pending_received,
            'pending_mutual_groups': pending_mutual_groups,
            'sent_requests': sent_requests,
        })

    elif tab == 'all':
        context['is_unverified'] = not request.user.email_verified

        if request.user.email_verified:
            from django.core.paginator import Paginator

            blocked_ids = Block.get_blocked_user_ids(request.user)
            queryset = User.objects.exclude(
                pk__in=[request.user.pk] + list(blocked_ids),
            ).filter(
                deleted_at__isnull=True,
                is_superuser=False,
                show_in_search=True,
            ).order_by('username')

            query = request.GET.get('q', '').strip()
            if query:
                queryset = queryset.filter(username__icontains=query)

            paginator = Paginator(queryset, 25)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)

            context.update({
                'page_obj': page_obj,
                'query': query,
            })

    return render(request, 'club/users_page.html', context)


def user_search(request):
    from django.http import QueryDict
    query = request.GET.get('q', '').strip()
    params = QueryDict(mutable=True)
    params['tab'] = 'all'
    if query:
        params['q'] = query
    return redirect(f'/users/?{params.urlencode()}', permanent=True)


@login_required
def friends_list(request, username):
    profile_user = get_object_or_404(User, username__iexact=username)
    if profile_user != request.user and not profile_user.show_friends:
        raise PermissionDenied
    friends = Friendship.get_friends_of(profile_user)
    if profile_user == request.user:
        blocked_ids = Block.get_blocked_user_ids(request.user)
        friends = friends.exclude(pk__in=blocked_ids)
    return render(request, 'club/friends_list.html', {
        'profile_user': profile_user,
        'friends': friends,
    })


# ---------------------------------------------------------------------------
# Private event views
# ---------------------------------------------------------------------------

@login_required
def private_event_create(request):
    if not can_create_private_event(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = PrivateEventForm(request.POST, creator=request.user)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.date = form.cleaned_data['date']
            offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0
            event.voting_deadline_offset_minutes = offset
            custom_deadline = form.cleaned_data.get('voting_deadline')
            if custom_deadline:
                event.voting_deadline = custom_deadline
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.duration_minutes = form.cleaned_data.get('duration_minutes') or 120
            event.save()
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            if tag_id_list:
                event.tags.set(tag_id_list)
            co_creator_ids = form.cleaned_data.get('co_creator_id_list', [])
            if co_creator_ids:
                co_creators = User.objects.filter(pk__in=co_creator_ids)
                for cc in co_creators:
                    event.co_creators.add(cc)
                    EventAttendance.objects.get_or_create(user=cc, event=event)
                    notify_event_co_creator(cc, event, request.user)
            PrivateEventCreationLog.objects.create(user=request.user, event=event)
            return redirect('private_event_detail', pk=event.pk)
    else:
        form = PrivateEventForm(initial={
            'voting_deadline_offset_minutes': SiteSettings.load().default_voting_offset_minutes,
            'duration_minutes': SiteSettings.load().default_event_duration_minutes,
        }, creator=request.user)

    blocked_ids = Block.get_blocked_user_ids(request.user)
    friends = Friendship.get_friends_of(request.user).exclude(pk__in=blocked_ids)

    return render(request, 'club/private_event_form.html', {
        'form': form,
        'action': 'Create',
        'voting_offset': SiteSettings.load().default_voting_offset_minutes,
        'initial_tags': [],
        'friends': friends,
        'max_co_creators': SiteSettings.load().max_co_creators,
    })


def private_event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_detail', slug=event.group.slug, pk=event.pk)

    if not can_view_private_event(request.user, event):
        raise PermissionDenied

    event.sync_voting_status()
    event.refresh_from_db()

    attendees = EventAttendance.objects.filter(event=event).select_related('user')

    is_attending = False
    if request.user.is_authenticated:
        is_attending = EventAttendance.objects.filter(
            user=request.user, event=event,
        ).exists()

    can_resume = (
        not event.voting_open
        and event.is_currently_active
        and timezone.now() < event.voting_deadline
    )

    is_organizer_user = (
        request.user.is_authenticated
        and event.is_organizer(request.user)
    )

    is_creator = (
        request.user.is_authenticated
        and event.created_by == request.user
    )

    game_sessions = GameSession.objects.filter(event=event).select_related('board_game').prefetch_related('players', 'players__user')
    return render(request, 'club/private_event_detail.html', {
        'event': event,
        'attendees': attendees,
        'is_attending': is_attending,
        'time_midnight': dt_time(0, 0),
        'can_resume': can_resume,
        'is_organizer': is_organizer_user,
        'is_creator': is_creator,
        'game_sessions': game_sessions,
    })


@login_required
def private_event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_edit', slug=event.group.slug, pk=event.pk)

    if not event.is_organizer(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = PrivateEventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save(commit=False)
            if not event.is_ongoing:
                event.duration_minutes = form.cleaned_data.get('duration_minutes') or 120
            event.date = form.cleaned_data['date']
            offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0
            event.voting_deadline_offset_minutes = offset
            custom_deadline = form.cleaned_data.get('voting_deadline')
            if custom_deadline:
                event.voting_deadline = custom_deadline
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.save()
            tag_id_list = form.cleaned_data.get('tag_id_list', [])
            event.tags.set(tag_id_list)
            return redirect('private_event_detail', pk=event.pk)
    else:
        form = PrivateEventForm(instance=event, initial={
            'voting_deadline_offset_minutes': event.voting_deadline_offset_minutes,
        })

    return render(request, 'club/private_event_form.html', {
        'form': form,
        'action': 'Edit',
        'voting_offset': event.voting_deadline_offset_minutes,
        'event': event,
        'initial_tags': list(event.tags.all()),
    })


@login_required
def event_settings(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        raise PermissionDenied

    if not can_edit_private_event_settings(request.user, event):
        raise PermissionDenied

    if request.method == 'POST':
        form = EventSettingsForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            return redirect('private_event_detail', pk=event.pk)
    else:
        form = EventSettingsForm(instance=event)

    attendees = EventAttendance.objects.filter(
        event=event,
    ).exclude(user=event.created_by).select_related('user')

    return render(request, 'club/private_event_settings.html', {
        'form': form,
        'event': event,
        'attendees': attendees,
    })


@login_required
def private_event_rsvp(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_rsvp', slug=event.group.slug, pk=event.pk)

    if not can_rsvp_private_event(request.user, event):
        raise PermissionDenied

    _rsvp_toggle(request.user, event)

    return redirect('private_event_detail', pk=event.pk)


@login_required
def private_event_vote(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_vote', slug=event.group.slug, pk=event.pk)

    if not can_view_private_event(request.user, event):
        raise PermissionDenied

    if not EventAttendance.objects.filter(user=request.user, event=event).exists():
        raise PermissionDenied

    event.sync_voting_status()
    event.refresh_from_db()

    games = event.get_game_pool()
    game_count = games.count()

    existing_votes = Vote.objects.filter(
        user=request.user, event=event,
    ).select_related('board_game').order_by('rank')
    vote_data = []
    for vote in existing_votes:
        vote_data.append({
            'board_game': vote.board_game_id,
            'rank': vote.rank,
            'game_name': vote.board_game.name,
        })

    if not event.is_voting_open:
        if request.method == 'POST':
            return render(request, 'club/event_vote.html', {
                'event': event,
                'games': games,
                'game_count': game_count,
                'vote_data': vote_data,
                'voting_closed': True,
                'mid_submit_closed': True,
            })
        return render(request, 'club/event_vote.html', {
            'event': event,
            'games': games,
            'game_count': game_count,
            'vote_data': vote_data,
            'voting_closed': True,
            'mid_submit_closed': False,
        })

    if request.method == 'POST':
        entries, errors = _validate_vote_submissions(request.POST, games)
        if errors:
            return render(request, 'club/event_vote.html', {
                'event': event,
                'games': games,
                'game_count': game_count,
                'vote_data': vote_data,
                'voting_closed': False,
                'mid_submit_closed': False,
                'vote_errors': errors,
            })
        Vote.objects.filter(user=request.user, event=event).delete()
        for game_id, rank in entries:
            Vote.objects.create(
                user=request.user,
                event=event,
                board_game_id=game_id,
                rank=rank,
            )
        return redirect('private_event_detail', pk=event.pk)

    return render(request, 'club/event_vote.html', {
        'event': event,
        'games': games,
        'game_count': game_count,
        'voting_closed': False,
        'mid_submit_closed': False,
    })


def private_event_results(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_results', slug=event.group.slug, pk=event.pk)

    if not event.is_organizer(request.user):
        if not (request.user.is_superuser or request.user.is_site_admin):
            raise PermissionDenied

    scores = calculate_borda_scores(event)
    game_map = {g.pk: g for g in BoardGame.objects.filter(pk__in=scores.keys())}

    results = []
    for game_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        results.append({
            'game': game_map[game_id],
            'score': score,
        })

    show_individual = event.show_individual_votes
    individual_votes = None
    if show_individual:
        attendee_ids = EventAttendance.objects.filter(
            event=event,
        ).values_list('user_id', flat=True)
        votes = Vote.objects.filter(
            event=event, user_id__in=attendee_ids,
        ).select_related('user', 'board_game').order_by('user', 'rank')
        user_votes = {}
        for vote in votes:
            user_votes.setdefault(vote.user, []).append(vote)
        individual_votes = user_votes

    return render(request, 'club/event_results.html', {
        'event': event,
        'results': results,
        'show_individual': show_individual,
        'individual_votes': individual_votes,
    })


@login_required
def private_event_toggle_voting(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_toggle_voting', slug=event.group.slug, pk=event.pk)

    if not event.is_organizer(request.user):
        raise PermissionDenied

    event.sync_voting_status()
    event.refresh_from_db()

    if event.is_voting_open:
        event.voting_open = False
        event.save()
    else:
        if not event.is_active:
            return redirect('private_event_detail', pk=event.pk)
        if timezone.now() >= event.voting_deadline:
            return redirect('private_event_detail', pk=event.pk)
        event.voting_open = True
        event.save()

    return redirect('private_event_detail', pk=event.pk)


@login_required
def private_event_toggle_visibility(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        return redirect('event_toggle_visibility', slug=event.group.slug, pk=event.pk)

    if not event.is_organizer(request.user):
        raise PermissionDenied

    event.show_individual_votes = not event.show_individual_votes
    event.save()
    return redirect('private_event_detail', pk=event.pk)


@login_required
def event_invite(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if event.group_id is not None:
        raise PermissionDenied

    if not can_invite_to_event(request.user, event):
        raise PermissionDenied

    if request.method == 'POST':
        form = EventInviteForm(request.POST)
        if form.is_valid():
            user_ids = form.cleaned_data['user_ids']
            blocked_ids = Block.get_blocked_user_ids(request.user)
            for uid in user_ids:
                if uid in blocked_ids:
                    continue
                target = User.objects.filter(pk=uid).first()
                if target and target != request.user:
                    _, created = EventInvite.objects.get_or_create(
                        event=event, user=target,
                        defaults={'invited_by': request.user},
                    )
                    if created:
                        notify_event_invite_sent(target, request.user, event)
            return redirect('private_event_detail', pk=event.pk)
    else:
        form = EventInviteForm()

    blocked_ids = Block.get_blocked_user_ids(request.user)
    friends = Friendship.get_friends_of(request.user).exclude(pk__in=blocked_ids)

    return render(request, 'club/event_invite.html', {
        'form': form,
        'event': event,
        'friends': friends,
    })


@login_required
def event_invite_respond(request, pk, invite_pk, status):
    invite = get_object_or_404(EventInvite, pk=invite_pk)

    if invite.user != request.user:
        raise PermissionDenied

    if invite.status != 'pending':
        raise PermissionDenied

    if request.method == 'POST':
        if status == 'accept':
            invite.accept()
            notify_event_invite_accepted(invite.invited_by, request.user, invite.event)
        elif status == 'decline':
            invite.decline()
            notify_event_invite_declined(invite.invited_by, request.user, invite.event)
        return redirect('private_event_detail', pk=invite.event.pk)

    return redirect('notification_list')


# ---------------------------------------------------------------------------
# Tag views
# ---------------------------------------------------------------------------

@login_required
def game_tag_search(request):
    query = request.GET.get('q', '').strip().lower()
    qs = GameTag.objects.annotate(
        count=Count('tagged_games'),
    ).order_by('-count', 'name')
    if query:
        qs = qs.filter(name__icontains=query)
    tags = qs.values('pk', 'name', 'count')[:25]
    return JsonResponse(
        [{'id': t['pk'], 'name': t['name'], 'count': t['count']} for t in tags],
        safe=False,
    )


@login_required
def event_tag_search(request):
    query = request.GET.get('q', '').strip().lower()
    qs = EventTag.objects.annotate(
        count=Count('tagged_events'),
    ).order_by('-count', 'name')
    if query:
        qs = qs.filter(name__icontains=query)
    tags = qs.values('pk', 'name', 'count')[:25]
    return JsonResponse(
        [{'id': t['pk'], 'name': t['name'], 'count': t['count']} for t in tags],
        safe=False,
    )


@login_required
def tag_request_submit(request):
    import json as _json
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    user = request.user
    if not user.email_verified:
        raise PermissionDenied
    if user.is_superuser or user.is_site_admin:
        raise PermissionDenied

    try:
        body = _json.loads(request.body)
    except (_json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = body.get('name', '').strip().lower()
    tag_type = body.get('tag_type', '').strip()

    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    if len(name) > TAG_MAX_LENGTH:
        return JsonResponse({'error': f'Name must be {TAG_MAX_LENGTH} characters or less'}, status=400)
    if tag_type not in ('game', 'event'):
        return JsonResponse({'error': 'Invalid tag type'}, status=400)

    if GameTag.objects.filter(name=name).exists() if tag_type == 'game' else EventTag.objects.filter(name=name).exists():
        return JsonResponse({'error': 'Tag already exists'}, status=400)

    if TagRequest.objects.filter(name=name, tag_type=tag_type, status='pending').exists():
        return JsonResponse({'error': 'A pending request for this tag already exists'}, status=400)

    req = TagRequest.objects.create(name=name, tag_type=tag_type, requested_by=user)
    return JsonResponse({'status': 'submitted', 'name': req.name, 'tag_type': req.tag_type})


def _tag_admin_required(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not (request.user.is_superuser or request.user.is_site_admin):
        raise PermissionDenied
    return None


def admin_tags(request):
    redirect_resp = _tag_admin_required(request)
    if redirect_resp:
        return redirect_resp

    tab = request.GET.get('tab', 'game')
    if tab not in ('game', 'event', 'requests'):
        tab = 'game'

    game_tags = GameTag.objects.all()
    event_tags = EventTag.objects.all()
    pending_requests = TagRequest.objects.filter(status='pending').select_related('requested_by')

    return render(request, 'club/admin_tags.html', {
        'game_tags': game_tags,
        'event_tags': event_tags,
        'pending_requests': pending_requests,
        'tab': tab,
    })


def admin_tag_add(request, tag_type):
    import json as _json
    redirect_resp = _tag_admin_required(request)
    if redirect_resp:
        return redirect_resp

    if request.method != 'POST':
        return redirect('admin_tags')

    if tag_type not in ('game', 'event'):
        return JsonResponse({'error': 'Invalid tag type'}, status=400)

    try:
        body = _json.loads(request.body)
    except (_json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = body.get('name', '').strip().lower()
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    if len(name) > TAG_MAX_LENGTH:
        return JsonResponse({'error': f'Name must be {TAG_MAX_LENGTH} characters or less'}, status=400)

    model = GameTag if tag_type == 'game' else EventTag
    if model.objects.filter(name=name).exists():
        return JsonResponse({'error': 'Tag already exists'}, status=400)

    tag = model.objects.create(name=name, created_by=request.user)
    return JsonResponse({'id': tag.pk, 'name': tag.name})


def admin_tag_delete(request, tag_type, pk):
    redirect_resp = _tag_admin_required(request)
    if redirect_resp:
        return redirect_resp

    if not request.user.is_superuser:
        raise PermissionDenied

    if tag_type not in ('game', 'event'):
        raise Http404

    model = GameTag if tag_type == 'game' else EventTag
    tag = get_object_or_404(model, pk=pk)

    if request.method == 'POST':
        tag.delete()
        return redirect('admin_tags')

    if tag_type == 'game':
        usage_count = tag.tagged_games.count()
    else:
        usage_count = tag.tagged_events.count()

    return render(request, 'club/admin_tag_delete_confirm.html', {
        'tag': tag,
        'tag_type': tag_type,
        'usage_count': usage_count,
    })


def admin_tag_request_approve(request, pk):
    redirect_resp = _tag_admin_required(request)
    if redirect_resp:
        return redirect_resp

    if request.method != 'POST':
        return redirect('admin_tags')

    req = get_object_or_404(TagRequest, pk=pk, status='pending')
    req.status = 'approved'
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save()

    model = GameTag if req.tag_type == 'game' else EventTag
    tag, _ = model.objects.get_or_create(name=req.name, defaults={'created_by': request.user})

    Notification.objects.create(
        user=req.requested_by,
        message=f'Your tag request "{req.name}" has been approved.',
        notification_type='tag_request_approved',
    )

    return redirect('admin_tags')


def admin_tag_request_reject(request, pk):
    redirect_resp = _tag_admin_required(request)
    if redirect_resp:
        return redirect_resp

    if request.method != 'POST':
        return redirect('admin_tags')

    req = get_object_or_404(TagRequest, pk=pk, status='pending')
    req.status = 'rejected'
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save()

    return redirect('admin_tags')


def _get_feedback_connection():
    if getattr(settings, 'SEND_REAL_EMAILS', False):
        from django.core.mail import get_connection
        return get_connection(backend='django.core.mail.backends.smtp.EmailBackend')
    return None


def feedback(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.email_verified:
        from django.contrib import messages
        messages.error(request, 'You must verify your email before submitting feedback.')
        return redirect('dashboard')

    target_email = getattr(settings, 'FEEDBACK_TARGET_EMAIL', '')
    if not target_email:
        return render(request, 'club/feedback.html', {
            'form': None,
            'unavailable': True,
        })

    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback_type = form.cleaned_data['feedback_type']
            email = form.cleaned_data['email']
            message = form.cleaned_data['message']
            type_display = dict(FEEDBACK_TYPE_CHOICES).get(feedback_type, feedback_type)
            subject = f'[Board Game Club Feedback] {type_display} — from {request.user.username}'
            body = (
                f'Feedback Type: {type_display}\n'
                f'From: {request.user.username}\n'
                f'Email: {email}\n\n'
                f'{message}'
            )
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [target_email],
                connection=_get_feedback_connection(),
            )
            from django.contrib import messages
            messages.success(request, 'Thank you for your feedback!')
            return redirect('feedback')
    else:
        form = FeedbackForm(initial={'email': request.user.email})

    return render(request, 'club/feedback.html', {
        'form': form,
        'unavailable': False,
    })


@login_required
def event_summary(request, pk):
    event = get_object_or_404(Event, pk=pk)
    is_org = _is_event_organizer(request.user, event)
    is_group_admin = (
        event.group_id is not None
        and event.group.is_admin(request.user)
    )
    if not is_org and not is_group_admin and not request.user.is_superuser and not request.user.is_site_admin:
        raise PermissionDenied

    if event.phase != 'completed':
        from django.contrib import messages
        messages.error(request, 'Event summary is only available after the event ends.')
        if event.group_id is not None:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        return redirect('private_event_detail', pk=event.pk)

    sessions = GameSession.objects.filter(event=event).select_related('board_game').prefetch_related('players')

    attendee_ids = set(
        EventAttendance.objects.filter(event=event).values_list('user_id', flat=True)
    )
    attendees = User.objects.filter(pk__in=attendee_ids)

    games_data = []
    for session in sessions:
        game = session.board_game
        pending_proposal = GameOwnershipProposal.objects.filter(
            board_game=game, status='pending',
        ).select_related('proposed_owner', 'proposed_group').first()
        declined_proposals = GameOwnershipProposal.objects.filter(
            board_game=game, status='declined',
        ).exists()

        games_data.append({
            'session': session,
            'game': game,
            'is_temporary': game.is_temporary,
            'has_owner': game.owner is not None or game.group is not None,
            'pending_proposal': pending_proposal,
            'was_declined': declined_proposals,
        })

    context = {
        'event': event,
        'games_data': games_data,
        'attendees': attendees,
    }
    return render(request, 'club/event_summary.html', context)


@login_required
def game_add_to_library(request, pk):
    game = get_object_or_404(BoardGame, pk=pk)
    if not game.is_temporary:
        from django.contrib import messages
        messages.error(request, 'This game is already in a library.')
        return redirect('game_list')

    event_id = request.GET.get('event')
    event = get_object_or_404(Event, pk=event_id) if event_id else None

    if event:
        is_org = _is_event_organizer(request.user, event)
        is_group_admin = (
            event.group_id is not None
            and event.group.is_admin(request.user)
        )
        if not is_org and not is_group_admin and not request.user.is_superuser and not request.user.is_site_admin:
            raise PermissionDenied

    if request.method == 'POST':
        owner_type = request.POST.get('owner_type')
        owner_id = request.POST.get('owner_id', '').strip()

        if owner_type == 'self':
            game.owner = request.user
            game.is_temporary = False
            game.save(update_fields=['owner', 'is_temporary'])
            from django.contrib import messages
            messages.success(request, f'"{game.name}" added to your library.')
            if event:
                if event.group_id is not None:
                    return redirect('event_summary', pk=event.pk)
                return redirect('event_summary', pk=event.pk)
            return redirect('game_list')

        elif owner_type == 'group' and event and event.group:
            game.group = event.group
            game.is_temporary = False
            game.save(update_fields=['group', 'is_temporary'])
            from django.contrib import messages
            messages.success(request, f'"{game.name}" added to the group library.')
            if event.group_id is not None:
                return redirect('event_summary', pk=event.pk)
            return redirect('event_summary', pk=event.pk)

        elif owner_type == 'attendee' and owner_id:
            target_user = get_object_or_404(User, pk=owner_id)
            proposal = GameOwnershipProposal.objects.create(
                board_game=game,
                proposed_owner=target_user,
                proposed_by=request.user,
                event=event,
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )
            from .notifications import notify_game_ownership_proposed
            notify_game_ownership_proposed(target_user, game, event, request.user)
            from django.contrib import messages
            messages.success(request, f'Proposal sent to {target_user.username}.')
            if event:
                if event.group_id is not None:
                    return redirect('event_summary', pk=event.pk)
                return redirect('event_summary', pk=event.pk)
            return redirect('game_list')

    attendee_ids = set()
    if event:
        attendee_ids = set(
            EventAttendance.objects.filter(event=event).values_list('user_id', flat=True)
        )
    attendees = User.objects.filter(pk__in=attendee_ids).exclude(pk=request.user.pk)

    context = {
        'game': game,
        'event': event,
        'attendees': attendees,
    }
    return render(request, 'club/game_owner_selection.html', context)


@login_required
def game_add_to_library_save(request, pk):
    game = get_object_or_404(BoardGame, pk=pk)
    if not game.is_temporary:
        from django.contrib import messages
        messages.error(request, 'This game is already in a library.')
        return redirect('game_list')

    event_id = request.GET.get('event')
    event = get_object_or_404(Event, pk=event_id) if event_id else None

    if request.method == 'POST':
        form = BoardGameForm(request.POST, instance=game, ownership_user=request.user)
        if form.is_valid():
            game = form.save(commit=False)
            ownership_target = form.cleaned_data.get('ownership_target', 'self')

            if ownership_target == 'self':
                game.owner = request.user
            elif ownership_target.startswith('group:'):
                slug = ownership_target[len('group:'):]
                group = Group.objects.get(slug=slug)
                game.owner = None
                game.group = group

            game.is_temporary = False
            game.save()

            tag_ids = form.cleaned_data.get('tag_id_list', [])
            if tag_ids:
                game.tags.set(tag_ids)

            from django.contrib import messages
            messages.success(request, f'"{game.name}" added to library.')
            if event:
                return redirect('event_summary', pk=event.pk)
            return redirect('game_list')
    else:
        form = BoardGameForm(instance=game, ownership_user=request.user)

    context = {
        'form': form,
        'game': game,
        'event': event,
    }
    return render(request, 'club/game_add_to_library_form.html', context)


@login_required
def game_proposal_accept(request, pk):
    proposal = get_object_or_404(GameOwnershipProposal, pk=pk)
    if proposal.proposed_owner != request.user:
        raise PermissionDenied

    if proposal.status != 'pending':
        from django.contrib import messages
        messages.error(request, 'This proposal is no longer pending.')
        return redirect('notification_list')

    try:
        proposal.accept()
    except ValueError:
        from django.contrib import messages
        messages.error(request, 'This proposal has expired.')
        return redirect('notification_list')

    from .notifications import notify_game_ownership_accepted
    notify_game_ownership_accepted(proposal.proposed_by, proposal.board_game, request.user)

    from django.contrib import messages
    messages.success(request, f'"{proposal.board_game.name}" added to your library.')
    return redirect('notification_list')


@login_required
def game_proposal_decline(request, pk):
    proposal = get_object_or_404(GameOwnershipProposal, pk=pk)
    if proposal.proposed_owner != request.user:
        raise PermissionDenied

    if proposal.status != 'pending':
        from django.contrib import messages
        messages.error(request, 'This proposal is no longer pending.')
        return redirect('notification_list')

    proposal.decline()

    from .notifications import notify_game_ownership_declined
    notify_game_ownership_declined(proposal.proposed_by, proposal.board_game, request.user)

    from django.contrib import messages
    messages.info(request, f'Proposal for "{proposal.board_game.name}" declined.')
    return redirect('notification_list')


def privacy_policy(request):
    return render(request, 'club/privacy_policy.html')
