from datetime import datetime, time as dt_time

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import BoardGame, Event, VerifiedIcon, Vote
from .timezone_utils import get_timezone_choices, is_valid_timezone
from .utils import MAX_FILE_SIZE, parse_bgg_link, validate_image_size

User = get_user_model()


class UserManageForm(forms.ModelForm):
    is_organizer = forms.BooleanField(required=False)
    is_site_admin = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ['is_organizer', 'is_site_admin']


class UserAddForm(forms.ModelForm):
    email = forms.EmailField(required=False)
    temporary_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
    )

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        temp_pw = cleaned_data.get('temporary_password')
        if not email and not temp_pw:
            raise forms.ValidationError(
                'Either an email address or a temporary password is required.'
            )
        if email and temp_pw:
            raise forms.ValidationError(
                'Provide either an email address or a temporary password, not both.'
            )
        return cleaned_data


class SetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label='New password',
        widget=forms.PasswordInput,
    )
    new_password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('new_password1') != cleaned_data.get('new_password2'):
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ['username', 'email']


class EmailOrUsernameLoginForm(AuthenticationForm):
    username = forms.CharField(label='Email or Username')


class BoardGameForm(forms.ModelForm):
    bgg_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    bgg_link_input = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Paste a BoardGameGeek URL or ID (e.g. https://boardgamegeek.com/boardgame/13/catan)',
        }),
    )
    complexity = forms.ChoiceField(
        choices=[('', '---')] + BoardGame.COMPLEXITY_CHOICES,
        required=True,
    )
    min_players = forms.IntegerField(
        required=True,
        min_value=1,
        widget=forms.NumberInput(attrs={'min': '1', 'class': 'player-count-input'}),
    )
    max_players = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'min': '1', 'class': 'player-count-input'}),
    )
    max_players_unlimited = forms.BooleanField(required=False)

    class Meta:
        model = BoardGame
        fields = ['name', 'description', 'min_players', 'max_players', 'complexity', 'bgg_id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.bgg_link:
            self.fields['bgg_link_input'].initial = self.instance.bgg_link

    def clean_bgg_link_input(self):
        value = self.cleaned_data.get('bgg_link_input', '')
        if not value or not value.strip():
            return ''
        parsed = parse_bgg_link(value)
        if parsed is None:
            raise forms.ValidationError(
                'Enter a valid BoardGameGeek URL or numeric ID.'
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        min_p = cleaned_data.get('min_players')
        max_p = cleaned_data.get('max_players')
        unlimited = cleaned_data.get('max_players_unlimited')

        if min_p is not None and min_p < 1:
            self.add_error('min_players', 'Min players must be at least 1.')

        if unlimited:
            cleaned_data['max_players'] = 0
        elif not max_p and max_p != 0:
            self.add_error('max_players', 'Enter a max player count or check Unlimited.')
        elif min_p is not None and max_p is not None and max_p < min_p:
            self.add_error('max_players', 'Max players cannot be less than min players.')

        return cleaned_data


class EventForm(forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )
    voting_deadline_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    voting_deadline_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )
    voting_deadline_offset_minutes = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = Event
        fields = ['title', 'location', 'description']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.date:
            self.fields['date'].initial = self.instance.date.date()
            if self.instance.date.time() != dt_time(0, 0):
                self.fields['time'].initial = self.instance.date.time()
            if self.instance.voting_deadline:
                self.fields['voting_deadline_date'].initial = self.instance.voting_deadline.date()
                if self.instance.voting_deadline.time() != dt_time(0, 0):
                    self.fields['voting_deadline_time'].initial = self.instance.voting_deadline.time()

    def clean(self):
        cleaned_data = super().clean()
        date_val = cleaned_data.get('date')
        time_val = cleaned_data.get('time') or dt_time(0, 0)
        if date_val:
            combined = datetime.combine(date_val, time_val)
            combined = timezone.make_aware(combined) if timezone.is_naive(combined) else combined
            original_date = getattr(self.instance, 'date', None)
            is_same_datetime = (
                original_date
                and combined.date() == original_date.date()
                and combined.hour == original_date.hour
                and combined.minute == original_date.minute
            )
            if combined < timezone.now() and not is_same_datetime:
                self.add_error('date', 'The event date cannot be in the past.')
            cleaned_data['date'] = combined

        vd_date = cleaned_data.get('voting_deadline_date')
        vd_time = cleaned_data.get('voting_deadline_time') or dt_time(0, 0)
        if vd_date:
            vd_combined = datetime.combine(vd_date, vd_time)
            vd_combined = timezone.make_aware(vd_combined) if timezone.is_naive(vd_combined) else vd_combined
            event_date = cleaned_data.get('date')
            if event_date:
                if vd_combined > event_date:
                    self.add_error('voting_deadline_date', 'Voting deadline cannot be after the event start time.')
            buffer = timezone.now() + timezone.timedelta(minutes=2)
            original_deadline = getattr(self.instance, 'voting_deadline', None)
            deadline_unchanged = (
                original_deadline
                and vd_combined.date() == original_deadline.date()
                and vd_combined.hour == original_deadline.hour
                and vd_combined.minute == original_deadline.minute
            )
            if vd_combined < buffer and not deadline_unchanged:
                self.add_error('voting_deadline_date', 'Voting deadline must be at least 2 minutes from now.')
            cleaned_data['voting_deadline'] = vd_combined
        else:
            cleaned_data['voting_deadline'] = None

        return cleaned_data


class RecurringEventForm(forms.Form):
    title = forms.CharField(max_length=200)
    description = forms.CharField(
        max_length=2000, required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    location = forms.CharField(max_length=300, required=False)
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )
    end_type = forms.ChoiceField(
        choices=[('count', 'Number of events'), ('end_date', 'End date')],
        initial='count',
    )
    occurrence_count = forms.IntegerField(
        required=False, min_value=2, max_value=52,
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    voting_deadline_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    voting_deadline_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )
    voting_deadline_offset_minutes = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput,
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        time_val = cleaned_data.get('time') or dt_time(0, 0)
        end_type = cleaned_data.get('end_type')

        if start_date:
            combined = datetime.combine(start_date, time_val)
            combined = timezone.make_aware(combined) if timezone.is_naive(combined) else combined
            if combined < timezone.now():
                self.add_error('start_date', 'The start date cannot be in the past.')
            cleaned_data['start_datetime'] = combined

        if end_type == 'count':
            count = cleaned_data.get('occurrence_count')
            if not count:
                self.add_error('occurrence_count', 'Enter the number of events (2-52).')
        elif end_type == 'end_date':
            end_date = cleaned_data.get('end_date')
            if not end_date:
                self.add_error('end_date', 'Enter an end date.')
            elif start_date and end_date < start_date:
                self.add_error('end_date', 'End date must be on or after the start date.')
            elif end_date:
                end_combined = datetime.combine(end_date, dt_time(23, 59))
                end_combined = timezone.make_aware(end_combined) if timezone.is_naive(end_combined) else end_combined
                if end_combined < timezone.now():
                    self.add_error('end_date', 'End date cannot be in the past.')

        return cleaned_data


class VoteForm(forms.ModelForm):

    class Meta:
        model = Vote
        fields = ['board_game', 'rank']


class SettingsForm(forms.Form):
    email = forms.EmailField(required=False)
    timezone = forms.ChoiceField(
        choices=get_timezone_choices,
        initial='UTC',
    )
    verified_icon = forms.IntegerField(required=False)
    bio = forms.CharField(
        max_length=500, required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    profile_picture = forms.ImageField(required=False)
    show_games = forms.BooleanField(required=False)
    show_events = forms.BooleanField(required=False)
    show_date_joined = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['verified_icon'].widget = forms.Select(
            choices=[('', 'Default (checkmark)')] + [
                (icon.pk, icon.name) for icon in VerifiedIcon.objects.all().order_by('name')
            ],
        )

    def clean_timezone(self):
        tz = self.cleaned_data['timezone']
        if not is_valid_timezone(tz):
            raise forms.ValidationError('Invalid timezone.')
        return tz

    def clean_verified_icon(self):
        pk = self.cleaned_data.get('verified_icon')
        if not pk:
            return None
        try:
            return VerifiedIcon.objects.get(pk=pk)
        except VerifiedIcon.DoesNotExist:
            raise forms.ValidationError('Invalid icon selection.')

    def clean_profile_picture(self):
        file = self.cleaned_data.get('profile_picture')
        if file and not validate_image_size(file):
            raise forms.ValidationError('Image must be smaller than 2MB.')
        return file


class BetaAccessForm(forms.Form):
    access_code = forms.CharField(
        widget=forms.PasswordInput(attrs={'autofocus': True}),
    )


class VerifiedIconForm(forms.ModelForm):
    class Meta:
        model = VerifiedIcon
        fields = ['name', 'image']

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name and VerifiedIcon.objects.filter(name=name).exists():
            raise forms.ValidationError('An icon with this name already exists.')
        return name
