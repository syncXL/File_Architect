import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import google.generativeai as genai
from typing_extensions import TypedDict
import json
from typing import Annotated,Literal
from langgraph.graph.message import add_messages
from langchain_core.messages.tool import ToolMessage
from langchain_core.messages.ai import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from agent_utils.agent_skelenton import *
from langchain_google_genai import ChatGoogleGenerativeAI
from tools import *
import logging
import json
import time
import uuid
from functools import wraps
import traceback

# Then import normally
from agent_utils.agent_skelenton import *

class AgentLogger:
    def __init__(self, agent_name, log_level=logging.INFO, log_file=None):
        # Create logger
        self.logger = logging.getLogger(agent_name)
        self.logger.setLevel(log_level)
        
        # Create unique session ID
        self.session_id = str(uuid.uuid4())
        
        # Set up console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Set up file handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
        
        # Create custom formatter for console
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def _format_json(self, data):
        """Format data as JSON string if possible"""
        if data is None:
            return "None"
        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except:
            return str(data)
    
    def log_prompt(self, prompt, metadata=None):
        """Log a prompt sent to the LLM"""
        self.logger.info(f"PROMPT [{self.session_id}]: {prompt[:100]}...")
        if metadata:
            self.logger.debug(f"PROMPT_METADATA: {self._format_json(metadata)}")
    
    def log_response(self, response, metadata=None):
        """Log a response from the LLM"""
        self.logger.info(f"RESPONSE [{self.session_id}]: {str(response)[:100]}...")
        if metadata:
            self.logger.debug(f"RESPONSE_METADATA: {self._format_json(metadata)}")
    
    def log_tool_usage(self, tool_name, args, result=None, success=True):
        """Log tool invocation details"""
        log_data = {
            "tool": tool_name,
            "args": args,
            "success": success
        }
        if result:
            log_data["result"] = result
        
        self.logger.info(f"TOOL_USAGE [{self.session_id}]: {tool_name}")
        self.logger.debug(f"TOOL_DETAILS: {self._format_json(log_data)}")
    
    def log_agent_state(self, state_data):
        """Log the current state of the agent"""
        self.logger.info(f"AGENT_STATE [{self.session_id}]: State updated")
        self.logger.debug(f"STATE_DETAILS: {self._format_json(state_data)}")
    
    def log_reasoning(self, thought_process):
        """Log reasoning steps"""
        self.logger.info(f"REASONING [{self.session_id}]: Thought process")
        self.logger.debug(f"REASONING_DETAILS: {self._format_json(thought_process)}")
    
    def log_error(self, error, context=None):
        """Log errors with context"""
        error_info = {
            "error_type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "context": context
        }
        self.logger.error(f"ERROR [{self.session_id}]: {str(error)}")
        self.logger.debug(f"ERROR_DETAILS: {self._format_json(error_info)}")
    
    def log_performance(self, operation, metrics):
        """Log performance metrics"""
        self.logger.info(f"PERFORMANCE [{self.session_id}]: {operation}")
        self.logger.debug(f"METRICS: {self._format_json(metrics)}")
    
    def log_task(self, task_name, status, details=None):
        """Log task progress"""
        self.logger.info(f"TASK [{self.session_id}]: {task_name} - {status}")
        if details:
            self.logger.debug(f"TASK_DETAILS: {self._format_json(details)}")

# Function decorator for timing operations
def timing_log(logger):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                logger.log_performance(
                    func.__name__, 
                    {"duration": end_time - start_time, "success": True}
                )
                return result
            except Exception as e:
                end_time = time.time()
                logger.log_performance(
                    func.__name__,
                    {"duration": end_time - start_time, "success": False}
                )
                logger.log_error(e, {"function": func.__name__})
                raise
        return wrapper
    return decorator

class ArchitectState(BaseState):
    """State representing the state the collector conversation"""
    folderPaths: list[str]

class Architect(Agent):
    def __init__(self):
        super().__init__()
        self.SYSINT = (
            "system",
            "You are The File Architect, a specialized agent designed to organize folders and files. "
            "You can respond to greetings but make sure it is in a cold manner, ensure any task assigned to you is related to your job assigned to you, if not, respond with:"
            "'I do not have such capabilities to handle such questions, perhaps you should ask my brothers'"
            "If it is: Ensure a folder path was provided to you, if not, prompt the user to provide one, there can be situations that the user can't remember the path, if that happens"
            "Use the tool select_folder to assist user in getting the folder path"
            "Before executing the task, ask the user if he wants to add more folder to be organized"
            "Once the user is done with adding folders to organize, you are to start working on the job"
            "** STAGE 1: PREPARATION**"
            "- Activate track tool"
            "- Ensure the paths given are not children of one another, for example L://X/M and L://X, M is a child of X"
            "- If a children exist, report to the user stating the children and parent, then ask approval from the user you want to discard the children and use only the parent"
            "- Verify the folder paths you were given with verify_path"
            "- If any of the folders verification fails, report to the user and ensure you state the paths that the verification failed, then ask for the correct paths"
            "- If all of the verification were successful, ask the user whether you can transfer between the folders given"
            "- Store the root folders with self.file_class.store_root"
            "- Generate and store the folder structure of all folders with self.file_class.add_folders"
            "- Strip the chat by using strip, the message should be 'STAGE 1 concluded' also include the summary of this stage which must contain the root folders, permission to tranfer between folders"
            "- Proceed to stage 2"
            "** STAGE 2: EXPLORATION **"
            "- Activate track tool"
            "- Get the details of a folder to work on with self.file_class.next_folder()"
            "- If the value gotten is a zero '0', strip the chat and include message 'STAGE 2 concluded',then proceed to stage 3"
            "- Understand what the folder is created for, using various contexts such as: both the name of the folder and the contents within the folder"
            "- Identify if the folder is a special folder or a children of a special folder"
            "- Special folders include are but not limited to:"
            "   - Game Folders e.g Call of Duty"
            "   - Application Folders e.g Visual Studio Code"
            "   - Project folders such as Diabetes prediction"
            "   - Temporary folders such as temp __pycache__"
            "Files cannot be moved in and out of special folders"
            "- If you're not sure a folder is a Special Folder you can ask the user whether it is"
            "- If confirmed, use self.file_class.make_special tool, assign the root parent of the special folder as the argument, strip the chat with the message argument :'CURRENT STAGE : 2' then restart STAGE 2"
            "- If the folder is empty, report to the user, and recommend to delete"
            "- If the user approves of it, proceed to delete it with self.file_class.delete_folder"
            "- If you don't understand what the folder is meant to store, prompt the user what the folder is about, and what file type it is meant to store"
            "- Check if the folders are organized"
            "- Organized folders usually exhibit the following properties:"
            "   - All the subfolders within the folder must have organized property to have a value: True"
            "   - The files within the folder have uniform extensions"
            "- After that compile what you know about the folder by stating:"
            "   - Description"
            "   - Expected File Type to be stored within it"
            "   - organized : Only True/False"
            "- Update the folder details with self.file_class.update_folder tool"
            "- strip the chat with the message argument :'CURRENT STAGE : 2'"
            "- Restart stage 2"
            "** STAGE 3: File Organization**"
            "- Activate track tool"
            "- Get the details of an unorganized folder to work on with self.file_class.next_ufolder()"
            "- If the value gotten is '0', strip the chat with the message argument having a value of 'STAGE 3 concluded', proceed to stage 4"
            "- Use the various properties of the subfolders and the contents of the subfolder to organize it"
            "- Determine the files/subfolder meets the requirements of staying within the folder if not, use list_folders then determine use that to determine the most suitable parent folder for such files/subfolder,however, you are to ask for permission for this"
            "- If the files does not even deserve to stay within a root folder move it to other root if its exists and correlates with the file , for example .mp4 file does not deserve to be in Document folder, it should be moved to Videos folder"
            "- For the files/subfolder within it, first check if it's possible to move them to existing subfolder only if they fit the description of the subfolder"
            "- If not use the other properties such as type and date to cluster them, create new folder if needs be"
            "- Report to the user, the approach you want to use organize the subfolder, to ask for the approval"
            "- If creating a new folder, ensure you also provide:"
            "   - Description"
            "   - Expected file to be stored within it"
            "   - organized: Must have a value of true"
            "- Once approved, execute it by using the various tools provided to you"
            "- Once done with organizing the you're folder currently on update the property, organized to True"
            "- strip the chat with the message argument :'CURRENT STAGE : 3'"
            "- Restart Stage 3"
            "** STAGE 4: Folder Restructuring **:"
            "- Activate track tool"
            "- Get the whole structure of the folder with get_structure"
            "- If the value gotten is '0', Respond to the user you are done with organizing and prompt him/her to check it out"
            "- If not:"
            "- Generate a new folder structure, grouping similar folders based on description"
            "- Report the new structure to the user, then ask for approval"
            "- If creating a new folder, ensure you also provide:"
            "   - Description"
            "   - Expected file to be stored within it"
            "   - organized: Must have a value of true"
            "- Once approved, execute your plan by using the various tools provided to you"
            "- strip the chat with the message argument :'CURRENT STAGE : 4'"
            "- Restart Stage 4"
            "Other tools given are:"
            "To create folder- use self.file_class.create_folder"
            "Move file with - self.file_class.move"
            "Move multiple files with the same extension with- self.file_class.filter_move"
            "Delete folder with self.file_class.delete_folder"
        )
        # file  explorer, once done with the task
        self.WELCOME_MSG = "Welcome User, What folder needs organizing"
        self.name = "The Collector"
        # store_root, add_folders, next_folder, make_special, delete_folder, update_folder, next_ufolder, get_structure,create_folder, move, filter_move, delete_path
        self.file_class = FileClass()
        auto_tools = [verify_path,self.file_class.store_root,self.file_class.add_folders,self.file_class.get_next_folder,self.file_class.make_special,
                    self.file_class.delete_folder,self.file_class.update_folder,self.file_class.get_next_ufolder,self.file_class.get_structure,
                    self.file_class.create_folder,self.file_class.move,self.file_class.filter_move,self.file_class.delete_path]
        self.manual_tools = [track, strip]
        self.auto_tools = ToolNode(auto_tools)
        self.n_tool_calls = 0
        self.bot = self.bot.bind_tools(auto_tools + self.manual_tools)

        self.bot_network = StateGraph(ArchitectState)
        self.build_network()

    def build_network(self):
        super().build_network()
        self.bot_network.add_node("tools",self.auto_tools)
        self.bot_network.add_node("manual_tools",self.manual_node)
        self.bot_network.add_edge("tools",self.name)
        self.bot_network.add_edge("manual_tools",self.name)
        self.bot_network.add_conditional_edges(self.name,self.use_tools)

    def manual_node(self,state: BaseState):
        tool_msg = state.get("messages", [])[-1]
        outbound_msgs = []

        for tool_call in tool_msg.tool_calls:
            if tool_call["name"] == "track":
                self.start_ind = len(state.get("messages",[])) -1
                response = "Tracking"

            elif tool_call["name"] == "strip":
                response = tool_call["args"]["message"]
                state["messages"] = state["messages"][:self.start_ind]

            outbound_msgs.append(
                ToolMessage(
                    content= response,
                    name=tool_call["name"],
                    tool_call_id = tool_call["id"]
                )
            )
        
        return {"messages" : outbound_msgs}

    def send_message(self,state: BaseState) -> BaseState:
        base_output = super().send_message(state=state)
        init_value = {"folderPaths" :{},"finished" : False}
        return init_value | base_output
        
    def use_tools(self, state: ArchitectState) -> Literal["human_node","tools","manual_tools"]:
        if not (msgs := state.get("messages", [])):
            raise ValueError(f"No messages found when parsing state: {state}")
        msg = msgs[-1]
        if state.get("finished",False):
            return END
        elif hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0:
            print(msg.tool_calls)
            if any(
            tool["name"] in self.auto_tools.tools_by_name.keys() for tool in msg.tool_calls):
                self.n_tool_calls = len(msg.tool_calls)
                return "tools"
            else:
                return "manual_tools"
        else:
            return "human_node"


the_warden_v0 = Architect()
# print(the_warden_v0.auto_tools.invoke(input=[AIMessage(content='I will start by listing the files and folders in the specified folders. Then, I will create a folder structure based on file types and move the files accordingly. Finally, I will present the proposed structure for your approval.\n', additional_kwargs={'function_call': {'name': 'list_files', 'arguments': '{"paths": ["C:/Users/VICTUS/Downloads"]}'}}, response_metadata={'prompt_feedback': {'block_reason': 0, 'safety_ratings': []}, 'finish_reason': 'STOP', 'safety_ratings': []}, id='run-72c84632-0d43-4297-b689-6b6d1714ab30-0', tool_calls=[{'name': 'list_files', 'args': {'paths': ['C:/Users/VICTUS/Documents']}, 'id': 'cfa36b75-b1df-47ce-8a60-1252acfdf640', 'type': 'tool_call'}, {'name': 'list_files', 'args': {'paths': ['C:/Users/VICTUS/Downloads']}, 'id': '2cd3eb81-1c98-4ea3-97e9-596b988ebcbc', 'type': 'tool_call'}], usage_metadata={'input_tokens': 1195, 'output_tokens': 69, 'total_tokens': 1264, 'input_token_details': {'cache_read': 0}})]))
print(the_warden_v0.start())