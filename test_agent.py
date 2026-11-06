# -*- coding: utf-8 -*-
"""
Created on Sat Oct 24 18:44:54 2026

@author: HP
"""

from services.agent_service import process_agent_command

def run_test():
    print("Testing L.E.O. Agent Service with Dual-API Fallback...\n")
    
    # Test a standard conversational prompt
    response_1 = process_agent_command("Status report, L.E.O.")
    print(f"User: Status report, L.E.O.")
    print(f"L.E.O.: {response_1}\n")
    
    # Test a system tool call route
    response_2 = process_agent_command("What is our current system health?")
    print(f"User: What is our current system health?")
    print(f"L.E.O.: {response_2}\n")

if __name__ == "__main__":
    run_test()