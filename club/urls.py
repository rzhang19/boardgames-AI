from django.contrib.auth import views as auth_views
from django.urls import path

from club import views
from club.forms import EmailOrUsernameLoginForm

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('beta-access/', views.beta_access, name='beta_access'),
    path('settings/', views.user_settings, name='user_settings'),
    path('save-timezone/', views.save_timezone, name='save_timezone'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html', authentication_form=EmailOrUsernameLoginForm), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('set-password/<str:token>/', views.user_set_password, name='user_set_password'),
    path('games/', views.game_list, name='game_list'),
    path('games/add/', views.game_add, name='game_add'),
    path('games/bgg-search/', views.bgg_search, name='bgg_search'),
    path('games/bgg-import/<int:bgg_id>/', views.bgg_import, name='bgg_import'),
    path('games/<int:pk>/', views.game_detail, name='game_detail'),
    path('games/<int:pk>/edit/', views.game_edit, name='game_edit'),
    path('games/<int:pk>/delete/', views.game_delete, name='game_delete'),
    path('events/', views.event_list, name='event_list'),
    path('events/add/', views.event_add, name='event_add'),
    path('events/<int:pk>/edit/', views.event_edit, name='event_edit'),
    path('events/<int:pk>/', views.event_detail, name='event_detail'),
    path('events/<int:pk>/rsvp/', views.event_rsvp, name='event_rsvp'),
    path('events/<int:pk>/vote/', views.event_vote, name='event_vote'),
    path('events/<int:pk>/results/', views.event_results, name='event_results'),
    path('events/<int:pk>/toggle-visibility/', views.event_toggle_visibility, name='event_toggle_visibility'),
    path('events/<int:pk>/toggle-voting/', views.event_toggle_voting, name='event_toggle_voting'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('manage-users/confirm/', views.manage_users_confirm, name='manage_users_confirm'),
    path('manage-users/cancel/', views.manage_users_cancel, name='manage_users_cancel'),
    path('manage-users/add/', views.user_add, name='user_add'),
    path('manage-users/<int:pk>/delete/', views.user_delete, name='user_delete'),
]
