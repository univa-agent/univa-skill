"""
CLI admin commands
"""

import click
import uuid
import toml
from tabulate import tabulate
from univa.config.config import auth_service, config, CONFIG_FILE


@click.group()
def admin():
    """Admin commands"""
    pass


@admin.command()
def init():
    """Initialize admin access code"""
    try:
        # Generate admin access code
        admin_code = str(uuid.uuid4())
        
        # Read existing configuration
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = toml.load(f)
        
        # Update admin access code
        cfg['admin_access_code'] = admin_code
        
        # Save configuration
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            toml.dump(cfg, f)
        
        click.echo("=" * 60)
        click.echo("Admin access code generated:")
        click.echo(f"  {admin_code}")
        click.echo("=" * 60)
        click.echo("⚠️  Please keep this access code safe!")
        click.echo("⚠️  This access code is used to manage all user access codes and system settings")
        click.echo()
        click.echo(f"Configuration saved to: {CONFIG_FILE}")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        import traceback
        traceback.print_exc()


@admin.command()
@click.option('--user-id', required=True, help='User ID')
@click.option('--description', default='', help='Description')
def add_user(user_id: str, description: str):
    """Add new user access code"""
    try:
        access_code = auth_service.add_access_code(user_id, description)
        
        click.echo("=" * 60)
        click.echo("✅ Access code created:")
        click.echo(f"  User ID:     {user_id}")
        click.echo(f"  Access Code: {access_code}")
        click.echo(f"  Description: {description}")
        click.echo("=" * 60)
        click.echo()
        click.echo("Please send this access code to the user. The user needs to include this access code in their requests.")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@admin.command()
def list_users():
    """List all user access codes"""
    try:
        codes = auth_service.list_access_codes()
        
        if not codes:
            click.echo("No access codes")
            return
        
        # Prepare table data
        table_data = []
        for code in codes:
            status = "✓" if code['enabled'] else "✗"
            table_data.append([
                status,
                code['user_id'],
                code['access_code'][:16] + "...",  # Only show first 16 characters
                code['description'],
                code['usage_count'],
                code['created_at'][:10] if code['created_at'] else 'N/A'
            ])
        
        # Display table
        headers = ["Status", "User ID", "Access Code", "Description", "Usage Count", "Created Date"]
        click.echo(f"\nTotal {len(codes)} access codes:\n")
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        click.echo()
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@admin.command()
@click.argument('access_code')
def show_user(access_code: str):
    """Show access code details"""
    try:
        info = auth_service.get_access_code_info(access_code)
        
        if not info:
            click.echo(f"❌ Access code does not exist: {access_code}", err=True)
            return
        
        click.echo("=" * 60)
        click.echo("Access code details:")
        click.echo(f"  User ID:      {info['user_id']}")
        click.echo(f"  Access Code:  {info['access_code']}")
        click.echo(f"  Description:  {info['description']}")
        click.echo(f"  Status:       {'Enabled' if info['enabled'] else 'Disabled'}")
        click.echo(f"  Created:      {info['created_at']}")
        click.echo(f"  Last Used:    {info['last_used'] or 'Never'}")
        click.echo(f"  Usage Count:  {info['usage_count']}")
        click.echo("=" * 60)
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@admin.command()
@click.argument('access_code')
def remove_user(access_code: str):
    """Delete user access code"""
    try:
        # Get access code information
        info = auth_service.get_access_code_info(access_code)
        if not info:
            click.echo(f"❌ Access code does not exist: {access_code}", err=True)
            return
        
        # Confirm deletion
        if click.confirm(f'Are you sure you want to delete the access code for user {info["user_id"]}?'):
            if auth_service.remove_access_code(access_code):
                click.echo(f"✅ Access code deleted: {access_code}")
            else:
                click.echo(f"❌ Deletion failed", err=True)
        else:
            click.echo("Cancelled")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@admin.command()
@click.argument('access_code')
@click.option('--enable/--disable', default=True, help='Enable or disable access code')
def toggle_user(access_code: str, enable: bool):
    """Enable/disable user access code"""
    try:
        if auth_service.enable_access_code(access_code, enable):
            action = "enabled" if enable else "disabled"
            click.echo(f"✅ Access code {action}: {access_code}")
        else:
            click.echo(f"❌ Access code does not exist: {access_code}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


@admin.command()
def show_config():
    """Show current configuration"""
    try:
        click.echo("=" * 60)
        click.echo("Current configuration:")
        click.echo(f"  Auth Enabled:           {config.get('auth_enabled', True)}")
        click.echo(f"  Session Timeout:        {config.get('session_timeout_minutes', 60)} minutes")
        click.echo(f"  Max Sessions Per User:  {config.get('max_sessions_per_user', 10)}")
        click.echo(f"  Auth Config File:       {config.get('auth_config_file', 'N/A')}")
        click.echo(f"  Admin Code Configured:  {'Yes' if config.get('admin_access_code') else 'No'}")
        click.echo("=" * 60)
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


if __name__ == '__main__':
    admin()