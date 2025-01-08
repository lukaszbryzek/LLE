#!/usr/bin/env python3
import rich_click as click
from inquirer import List, Text, prompt
from rich.console import Console
from rich import print as rprint
from typing import Dict, Optional, List as TypeList
import os
import sys
import subprocess
import re

console = Console()

class GitConfig:
    def __init__(self):
        self.options = {
            "source_branch": "",
            "target_branch": "",
            "commit_message": "",
            "pr_title": "",
            "pr_description": ""
        }
    
    def update_option(self, key: str, value: str):
        self.options[key] = value
    
    def get_option(self, key: str) -> str:
        return self.options[key]

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def execute_git_command(command: TypeList[str]) -> tuple[bool, str]:
    """Execute a git command and return success status and output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def get_current_branch() -> str:
    """Get the name of the current git branch."""
    success, output = execute_git_command(['git', 'branch', '--show-current'])
    return output if success else ""

def get_remote_branches() -> TypeList[str]:
    """Get list of all remote branches."""
    success, output = execute_git_command(['git', 'branch', '-r'])
    if not success:
        return []
    
    # Convert output to list and clean branch names
    branches = []
    for branch in output.split('\n'):
        branch = branch.strip()
        # Remove 'origin/' prefix and skip HEAD entry
        if branch and not branch.startswith('origin/HEAD'):
            branch = branch.replace('origin/', '', 1)
            branches.append(branch)
    
    return sorted(branches)

def is_valid_target_branch(source: str, target: str) -> bool:
    """
    Validate if target branch is a valid upgrade from source branch.
    Assumes environment branches follow pattern: env##
    """
    source_match = re.match(r'([a-z]+)(\d+)', source)
    target_match = re.match(r'([a-z]+)(\d+)', target)
    
    if not (source_match and target_match):
        return True  # Allow non-environment branches
    
    source_env = source_match.group(1)
    target_env = target_match.group(1)
    
    env_order = ['sbx', 'dev', 'uat']
    try:
        source_idx = env_order.index(source_env)
        target_idx = env_order.index(target_env)
        return target_idx > source_idx
    except ValueError:
        return True  # Allow unknown environment names

def get_menu_choices(config: GitConfig) -> Dict:
    clear_screen()
    menu_options = [
        ("Source Branch (current)", "source_branch"),
        ("Target Branch", "target_branch"),
        ("Commit Message", "commit_message"),
        ("PR Title", "pr_title"),
        ("PR Description", "pr_description")
    ]
    
    max_length = max(len(option[0]) for option in menu_options) + 2
    
    choices = [
        f"{display:<{max_length}} : [{config.get_option(key)}]"
        for display, key in menu_options
    ]
    
    choices.extend(['Review and Create PR', 'Exit'])
    
    questions = [
        List(
            'action',
            message='Select action',
            choices=choices,
        ),
    ]
    return prompt(questions)

def handle_branch_choice(current_branch: str) -> str:
    clear_screen()
    available_branches = get_remote_branches()
    valid_branches = [
        branch for branch in available_branches
        if is_valid_target_branch(current_branch, branch)
    ]
    
    if not valid_branches:
        rprint("[bold red]No valid target branches found![/]")
        return ""
        
    questions = [
        List(
            'branch',
            message='Select target branch',
            choices=valid_branches,
        ),
    ]
    return prompt(questions)['branch']

def handle_text_input(message: str, key: str) -> str:
    clear_screen()
    questions = [
        Text(key, message=message),
    ]
    return prompt(questions)[key]

def review_config(config: GitConfig) -> bool:
    clear_screen()
    rprint("[bold]Current configuration:[/]")
    for key, value in config.options.items():
        rprint(f"[cyan]{key}:[/] [green]{value}[/]")
    
    script_name = sys.argv[0]
    command_parts = [
        f"--{key.replace('_', '-')} \"{value}\""
        for key, value in config.options.items()
        if value
    ]
    command = f"python {script_name} " + " ".join(command_parts) + " --no-interactive"
    
    rprint("\n[yellow]Non-interactive command:[/]")
    rprint(f"[green]{command}[/]")
    
    questions = [
        List(
            'confirm',
            message='Is this configuration correct?',
            choices=['Yes, create PR', 'No, return to menu'],
        ),
    ]
    return prompt(questions)['confirm'].startswith('Yes')

def get_bitbucket_url() -> str:
    """Get Bitbucket repository URL."""
    success, output = execute_git_command(['git', 'config', '--get', 'remote.origin.url'])
    if not success:
        return ""
    return output.strip()

def create_pr(config: GitConfig) -> None:
    with console.status("[bold green]Processing..."):
        # Stage all changes
        success, output = execute_git_command(['git', 'add', '.'])
        if not success:
            rprint(f"[bold red]Error staging changes: {output}[/]")
            return

        # Create commit
        success, output = execute_git_command([
            'git', 'commit', '-m', config.get_option('commit_message')
        ])
        if not success:
            rprint(f"[bold red]Error creating commit: {output}[/]")
            return

        # Push changes
        current_branch = config.get_option('source_branch')
        success, output = execute_git_command(['git', 'push', 'origin', current_branch])
        if not success:
            rprint(f"[bold red]Error pushing changes: {output}[/]")
            return

        # Get Bitbucket URL and print PR creation instructions
        repo_url = get_bitbucket_url()
        if repo_url:
            # Convert SSH URL to HTTPS if necessary
            if repo_url.startswith('git@'):
                repo_url = repo_url.replace(':', '/').replace('git@', 'https://')
            if repo_url.endswith('.git'):
                repo_url = repo_url[:-4]
            
            rprint("[bold green]✓[/] Changes pushed successfully!")
            rprint("[yellow]Please create a pull request in Bitbucket:[/]")
            rprint(f"URL: {repo_url}/pull-requests/new")
            rprint("\n[bold]Pull Request details:[/]")
            rprint(f"Source branch: {config.get_option('source_branch')}")
            rprint(f"Target branch: {config.get_option('target_branch')}")
            rprint(f"Title: {config.get_option('pr_title')}")
            rprint(f"Description: {config.get_option('pr_description')}")
        else:
            rprint("[bold red]Could not determine repository URL[/]")

@click.command()
@click.option('--target-branch', type=str, help='Target branch name')
@click.option('--commit-message', type=str, help='Commit message')
@click.option('--pr-title', type=str, help='Pull request title')
@click.option('--pr-description', type=str, help='Pull request description')
@click.option('--interactive/--no-interactive', default=True, help='Run in interactive mode')
def main(target_branch: Optional[str], commit_message: Optional[str],
         pr_title: Optional[str], pr_description: Optional[str], 
         interactive: bool):
    """Git branch management and PR creation tool for Bitbucket"""
    
    config = GitConfig()
    current_branch = get_current_branch()
    
    if not current_branch:
        rprint("[bold red]Error: Could not determine current branch[/]")
        return
    
    # Set source branch as current branch
    config.update_option('source_branch', current_branch)
    
    if not interactive:
        # Use command line parameters
        if target_branch:
            config.update_option('target_branch', target_branch)
        if commit_message:
            config.update_option('commit_message', commit_message)
        if pr_title:
            config.update_option('pr_title', pr_title)
        if pr_description:
            config.update_option('pr_description', pr_description)
            
        create_pr(config)
        return

    # Interactive mode
    option_mapping = {
        'Target Branch': ('target_branch', 'Select target branch'),
        'Commit Message': ('commit_message', 'Enter commit message'),
        'PR Title': ('pr_title', 'Enter PR title'),
        'PR Description': ('pr_description', 'Enter PR description')
    }

    while True:
        choice = get_menu_choices(config)
        action = choice['action'].split(' : [')[0].strip()
        
        if action in option_mapping:
            key, message = option_mapping[action]
            if 'branch' in key:
                value = handle_branch_choice(current_branch)
            else:
                value = handle_text_input(message, key)
            config.update_option(key, value)
        elif action == 'Review and Create PR':
            if review_config(config):
                create_pr(config)
                break
        else:  # Exit
            break

if __name__ == '__main__':
    main()