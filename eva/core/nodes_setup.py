import asyncio
from config import logger
from typing import Dict, Any
from datetime import datetime

from eva.core.classes import EvaStatus
from eva.agent.classes import SetupNameOutput, SetupDesireOutput
from eva.core.ids import id_manager
from eva.utils.prompt import load_prompt, update_prompt

async def eva_setup(state: Dict[str, Any]) -> Dict[str, Any]:
    """ Setup the User Name """
    
    status = state["status"]
    agent = state["agent"]
    agent.set_tools([]) # disable tools for setup
    
    sense = state["sense"]
    language = sense.get("language")
    memory = state["memory"]

    history = memory.recall_conversation()
    timestamp = datetime.now()
    
    if status == EvaStatus.SETUP:
        prompt_template = "setup_one"
        output_format = SetupNameOutput
    elif status == "STEP2":
        prompt_template = "setup_two"
        output_format = SetupDesireOutput
        
    # get response from the LLM agent
    response = agent.respond(
        template=prompt_template,
        timestamp=timestamp,
        sense=sense,
        history=history,
        language=language,
        output_format=output_format
    )
    
    memory.create_memory(timestamp=timestamp, user_response=sense, response=response)
    action = response.get("action", [])
    speech = response.get("response")
    
    # send the response to the client device
    eva_response = {
        "speech": speech,
        "language": language,
        "wait": True if not action else False # determine if waiting for user, only for desktop client
    }
    
    client = state["client"]
    await client.send(eva_response)
    
    if status == EvaStatus.SETUP:
        name = response.get("name")
        confidence = float(response.get("confidence"))
        
        if name is not None and confidence >= 0.8:
            if hasattr(client, 'watcher'):
                await asyncio.to_thread(client.watcher.capture, save_file="P00001")
                id_manager.add_user(name, void="V00001", pid="P00001")
                await asyncio.to_thread(client.watcher.describer.identifier.initialize_ids)
                await asyncio.to_thread(client.listener.transcriber.identifier.initialize_recognizer)
            else:
                id_manager.add_user(name, void="V00001", pid="P00001")
            status = "STEP2"

    elif status == "STEP2":
        name = id_manager._void_list["V00001"]
        desire = response.get("desire")
        confidence = float(response.get("confidence"))
        if desire is not None and confidence >= 0.7:
            prompt = load_prompt("persona") + f"\nMy most important goal is to help {name} to achieve {desire}."
            update_prompt("persona", prompt)
            status = EvaStatus.THINKING

    # send the response to the client device
    num = state["num_conv"]
    await client.send_over()
    
    # Check if client supports save_file argument for receive
    import inspect
    sig = inspect.signature(client.receive)
    if "save_file" in sig.parameters:
        client_feedback = await client.receive(save_file="V00001")
    else:
        client_feedback = await client.receive()

    # check if the user wants to exit
    user_message = client_feedback.get("user_message")
    if user_message and any(word in user_message.lower() for word in ['bye', 'exit']):
        return {"status": EvaStatus.END}
    else:
        return {"status": status, "num_conv": num + 1, "sense": client_feedback}


def router_setup(state: Dict[str, Any]) -> str:
    """ Determine the next node based on the user input """
    
    status = state["status"]
    
    if status == EvaStatus.END:
        return "node_end"
    elif status == EvaStatus.THINKING: #finished setup
        return "node_converse"
    else:
        return "node_setup"