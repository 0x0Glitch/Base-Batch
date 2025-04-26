import json
import os
import sys
import time
from decimal import Decimal
from typing import Any, Optional

from coinbase_agentkit import (
    AgentKit,
    AgentKitConfig,
    EthAccountWalletProvider,
    EthAccountWalletProviderConfig,
    allora_action_provider,
    cdp_api_action_provider,
    cdp_wallet_action_provider,
    erc20_action_provider,
    pyth_action_provider,
    wallet_action_provider,
    weth_action_provider,
)
from coinbase_agentkit_langchain import get_langchain_tools
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from web3 import Web3
from web3.types import HexStr
from eth_account.account import Account

load_dotenv()

##################################################################
#                  NEW CONTRACT & ABI FOR CROSSCHAIN            #
##################################################################

CROSSCHAIN_CONTRACT_ADDRESS = ""

CROSSCHAIN_CONTRACT_ABI = [
    {
        "type": "constructor",
        "inputs": [
            {"name": "_aiAgent", "type": "address", "internalType": "address"},
            {"name": "_owner",   "type": "address", "internalType": "address"}
        ],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "aiAgent",
        "inputs": [],
        "outputs": [
            {"name": "", "type": "address", "internalType": "address"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "allowance",
        "inputs": [
            {"name": "owner",   "type": "address", "internalType": "address"},
            {"name": "spender", "type": "address", "internalType": "address"}
        ],
        "outputs": [
            {"name": "", "type": "uint256", "internalType": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "approve",
        "inputs": [
            {"name": "spender", "type": "address", "internalType": "address"},
            {"name": "value",   "type": "uint256", "internalType": "uint256"}
        ],
        "outputs": [
            {"name": "", "type": "bool", "internalType": "bool"}
        ],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "balanceOf",
        "inputs": [
            {"name": "account", "type": "address", "internalType": "address"}
        ],
        "outputs": [
            {"name": "", "type": "uint256", "internalType": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "crosschainBurn",
        "inputs": [
            {"name": "from",   "type": "address", "internalType": "address"},
            {"name": "amount", "type": "uint256", "internalType": "uint256"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "crosschainMint",
        "inputs": [
            {"name": "to",     "type": "address", "internalType": "address"},
            {"name": "amount", "type": "uint256", "internalType": "uint256"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "decimals",
        "inputs": [],
        "outputs": [
            {"name": "", "type": "uint8", "internalType": "uint8"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "deposit",
        "inputs": [],
        "outputs": [],
        "stateMutability": "payable"
    },
    {
        "type": "function",
        "name": "name",
        "inputs": [],
        "outputs": [
            {"name": "", "type": "string", "internalType": "string"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "owner",
        "inputs": [],
        "outputs": [
            {"name": "", "type": "address", "internalType": "address"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "renounceOwnership",
        "inputs": [],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "symbol",
        "inputs": [],
        "outputs": [
            {"name": "", "type": "string", "internalType": "string"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "totalSupply",
        "inputs": [],
        "outputs": [
            {"name": "", "type": "uint256", "internalType": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "transfer",
        "inputs": [
            {"name": "to",    "type": "address", "internalType": "address"},
            {"name": "value", "type": "uint256", "internalType": "uint256"}
        ],
        "outputs": [
            {"name": "", "type": "bool", "internalType": "bool"}
        ],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "transferFrom",
        "inputs": [
            {"name": "from",  "type": "address", "internalType": "address"},
            {"name": "to",    "type": "address", "internalType": "address"},
            {"name": "value", "type": "uint256", "internalType": "uint256"}
        ],
        "outputs": [
            {"name": "", "type": "bool", "internalType": "bool"}
        ],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "transferOwnership",
        "inputs": [
            {"name": "newOwner", "type": "address", "internalType": "address"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "withdraw",
        "inputs": [
            {"name": "amount", "type": "uint256", "internalType": "uint256"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    }
    # Events and errors omitted for brevity, but they won't break this code
]

##################################################################
#          HELPER FUNCTIONS: READ/WRITE ON THE NEW CONTRACT      #
##################################################################

def invoke_contract_function(
    wallet_provider: EthAccountWalletProvider,
    function_name: str,
    args: Optional[list] = None,
    value: Decimal = Decimal(0)
):
    """Generic function to invoke a write on the Crosschain contract."""
    try:
        web3 = Web3()
        contract = web3.eth.contract(
            address=CROSSCHAIN_CONTRACT_ADDRESS,
            abi=CROSSCHAIN_CONTRACT_ABI
        )

        if args is None:
            args = []

        data = contract.encode_abi(function_name, args=args)

        tx_params = {
            "to": HexStr(CROSSCHAIN_CONTRACT_ADDRESS),
            "data": HexStr(data),
        }
        # If payable, add ETH value
        if value > Decimal(0):
            tx_params["value"] = int(value * Decimal(10**18))

        tx_hash = wallet_provider.send_transaction(tx_params)
        wallet_provider.wait_for_transaction_receipt(tx_hash)
        return f"Successfully called {function_name}. TX hash: {tx_hash}"
    except Exception as e:
        return f"Error calling {function_name}: {str(e)}"


def read_contract_function(
    wallet_provider: EthAccountWalletProvider,
    function_name: str,
    args: Optional[list] = None
):
    """Generic function to read (call) on the Crosschain contract."""
    try:
        if args is None:
            args = []
        result = wallet_provider.read_contract(
            contract_address=CROSSCHAIN_CONTRACT_ADDRESS,
            abi=CROSSCHAIN_CONTRACT_ABI,
            function_name=function_name,
            args=args
        )
        return result
    except Exception as e:
        return f"Error reading from contract: {str(e)}"


##################################################################
#           WRAPPERS FOR THE RELEVANT CROSSCHAIN FUNCTIONS       #
##################################################################

def crosschain_mint(wallet_provider: EthAccountWalletProvider, to_address: str, amount: int):
    """
    Crosschain mint 'amount' tokens to 'to_address'.
    The contract's constructor sets _aiAgent who can do this. 
    We assume the agent is recognized as that _aiAgent.
    """
    return invoke_contract_function(
        wallet_provider,
        "crosschainMint",
        args=[to_address, amount]
    )

def crosschain_burn(wallet_provider: EthAccountWalletProvider, from_address: str, amount: int):
    """
    Crosschain burn 'amount' tokens from 'from_address'.
    Again, we assume the calling wallet is the recognized aiAgent.
    """
    return invoke_contract_function(
        wallet_provider,
        "crosschainBurn",
        args=[from_address, amount]
    )

def get_balance_of(wallet_provider: EthAccountWalletProvider, account: str):
    """Retrieve the token balance of a given account address."""
    return read_contract_function(wallet_provider, "balanceOf", args=[account])

def deposit_native_eth(wallet_provider: EthAccountWalletProvider, eth_amount: float):
    """Payable deposit of ETH into the contract (optional function)."""
    return invoke_contract_function(
        wallet_provider,
        "deposit",
        value=Decimal(str(eth_amount))
    )

def withdraw_tokens(wallet_provider: EthAccountWalletProvider, amount: int):
    """Withdraw 'amount' of base tokens from the contract. 
       This calls the 'withdraw(uint256)' function in the ABI.
    """
    return invoke_contract_function(wallet_provider, "withdraw", args=[amount])

##################################################################
#                  PARSING USER INPUT FOR TOOLS                  #
##################################################################

def parse_mint_args(input_str: str):
    """
    Expects: "TO_ADDRESS AMOUNT"
    Example: "0xReceiver 100000"
    """
    parts = input_str.strip().split()
    if len(parts) != 2:
        return "Error: Provide 'TO_ADDRESS AMOUNT'"
    to_addr, amt_str = parts
    try:
        amount_int = int(amt_str)
    except:
        return "Error: amount must be integer"
    return crosschain_mint(wallet_provider, to_addr, amount_int)

def parse_burn_args(input_str: str):
    """
    Expects: "FROM_ADDRESS AMOUNT"
    Example: "0xUser 50000"
    """
    parts = input_str.strip().split()
    if len(parts) != 2:
        return "Error: Provide 'FROM_ADDRESS AMOUNT'"
    from_addr, amt_str = parts
    try:
        amount_int = int(amt_str)
    except:
        return "Error: amount must be integer"
    return crosschain_burn(wallet_provider, from_addr, amount_int)

def parse_balance_of_args(input_str: str):
    """
    Expects: "ADDRESS"
    """
    address_str = input_str.strip()
    if not address_str:
        return "Error: Provide an address, e.g. 0x1234..."
    return get_balance_of(wallet_provider, address_str)

def parse_deposit_eth_args(input_str: str):
    """
    Expects: "0.01" or some float
    """
    eth_str = input_str.strip()
    try:
        eth_val = float(eth_str)
    except:
        return "Error: Provide a valid float like 0.001"
    return deposit_native_eth(wallet_provider, eth_val)

def parse_withdraw_args(input_str: str):
    """
    Expects: "AMOUNT_INTEGER"
    e.g. "100" => calls withdraw(100)
    """
    amt_str = input_str.strip()
    try:
        amt_int = int(amt_str)
    except:
        return "Error: Provide an integer for the amount"
    return withdraw_tokens(wallet_provider, amt_int)

##################################################################
#             INITIALIZE THE AGENT & SET UP THE TOOLS            #
##################################################################

def initialize_agent():
    llm = ChatOpenAI(model="gpt-4o")

    # Initialize wallet using private key from .env
    private_key = os.getenv("PRIVATE_KEY")
    assert private_key, "You must set the PRIVATE_KEY environment variable"
    assert private_key.startswith("0x"), "Private key must start with 0x hex prefix"
    
    # Create Ethereum account from private key
    account = Account.from_key(private_key)
    
    # Set up the wallet provider with the account
    global wallet_provider
    wallet_provider = EthAccountWalletProvider(
        config=EthAccountWalletProviderConfig(account=account, chain_id="84532")
    )

    # Setup the AgentKit
    agentkit = AgentKit(
        AgentKitConfig(
            wallet_provider=wallet_provider,
            action_providers=[
                cdp_api_action_provider(),
                cdp_wallet_action_provider(),
                erc20_action_provider(),
                pyth_action_provider(),
                wallet_action_provider(),
                weth_action_provider(),
                allora_action_provider(),
            ],
        )
    )

    # No need to save wallet data since we're using the private key from .env

    # Define the custom tools for crosschain calls
    custom_tools = [
        Tool(
            name="crosschain_mint",
            description=(
                "Crosschain-mint tokens into someone's address. Provide 'TO_ADDRESS AMOUNT'. "
                "Example: '0xReceiver 1000'. Must be recognized as aiAgent in the contract."
            ),
            func=parse_mint_args
        ),
        Tool(
            name="crosschain_burn",
            description=(
                "Crosschain-burn tokens from someone's address. Provide 'FROM_ADDRESS AMOUNT'. "
                "Example: '0xUser 5000'. Must be recognized as aiAgent in the contract."
            ),
            func=parse_burn_args
        ),
        Tool(
            name="balance_of",
            description=(
                "Get the token balance of a given address. Provide 'ADDRESS'. "
                "Example: '0x1234abcd...'."
            ),
            func=parse_balance_of_args
        ),
        Tool(
            name="deposit_eth",
            description=(
                "Deposit base ETH into the contract (payable). Provide float. Example: '0.01'"
            ),
            func=parse_deposit_eth_args
        ),
        Tool(
            name="withdraw",
            description=(
                "Withdraw base token from the contract. Provide an integer amount (uint256). Example: '100'"
            ),
            func=parse_withdraw_args
        ),
    ]

    # Combine standard AgentKit tools with custom ones
    tools = get_langchain_tools(agentkit) + custom_tools

    memory = MemorySaver()
    config = {"configurable": {"thread_id": "CDP Crosschain Agent Example!"}}

    # State modifier with additional detail about the agent’s purpose:
    detailed_state_modifier = (
        "\"You are an advanced on-chain agent specifically integrated with the 'Crosschain' "
        "ERC-20 contract deployed at 0xabc on the Base Sepolia network. "
        "Your on-chain identity (wallet address) is 0xbcd which is recognized as "
        "the 'aiAgent' in the contract's constructor.\n\n"
        "This contract is an ERC-20 token with extended crosschain capabilities. The key features include:\n"
        " - crosschainMint(to, amount): Mint tokens to a specific address.\n"
        " - crosschainBurn(from, amount): Burn tokens from a specific address.\n"
        " - deposit(), withdraw(uint256), transfer(...), etc., as typical ERC-20 or bridging operations.\n\n"
        "Your role is to validate user requests and convert them into precise contract function calls, ensuring:\n"
        "1. You only invoke functions allowed by your 'aiAgent' role.\n"
        "2. You parse numeric arguments correctly (especially for amounts) and pass them as raw integers.\n"
        "3. You handle the Base Sepolia chain environment, verifying if enough balance or gas is available for transactions.\n"
        "4. You provide thorough feedback to the user: for each invocation, return a transaction hash, or an error if something fails.\n\n"
        "Be mindful of security constraints, never reveal private keys, and carefully parse user inputs. \""
    )

    return create_react_agent(
        llm,
        tools=tools,
        checkpointer=memory,
        state_modifier=detailed_state_modifier
    ), config


##################################################################
#                   CHAT MODE & MAIN ENTRY POINT                 #
##################################################################

def run_chat_mode(agent_executor, config):
    print("Starting chat mode... Type 'exit' to end.")
    while True:
        try:
            user_input = input("\nPrompt: ")
            if user_input.lower() == "exit":
                break

            for chunk in agent_executor.stream({"messages": [HumanMessage(content=user_input)]}, config):
                if "agent" in chunk:
                    print(chunk["agent"]["messages"][0].content)
                elif "tools" in chunk:
                    print(chunk["tools"]["messages"][0].content)
                print("-------------------")

        except KeyboardInterrupt:
            print("Goodbye Agent!")
            sys.exit(0)


def main():
    agent_executor, config = initialize_agent()
    print("Starting in chat mode... Type 'exit' to end.")
    run_chat_mode(agent_executor, config)


if __name__ == "__main__":
    print("Starting Agent...")
    main()