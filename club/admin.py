from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, BoardGame, Event, EventAttendance, Notification, VerifiedIcon, Vote


admin.site.register(User, UserAdmin)


@admin.register(VerifiedIcon)
class VerifiedIconAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(BoardGame)
class BoardGameAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'group', 'complexity', 'bgg_weight', 'min_players', 'max_players', 'created_at')
    list_filter = ('owner', 'group', 'complexity')
    search_fields = ('name',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'location', 'created_by', 'is_active')
    list_filter = ('is_active', 'show_individual_votes')
    search_fields = ('title',)


@admin.register(EventAttendance)
class EventAttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'joined_at')
    list_filter = ('event',)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'board_game', 'rank')
    list_filter = ('event',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'notification_type', 'created_at')
    list_filter = ('is_read', 'notification_type')
    search_fields = ('user__username', 'message')
