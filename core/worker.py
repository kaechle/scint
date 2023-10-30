import json
import importlib
from typing import Dict, List, Any

from core.agent import Agent
from services.openai import completion
from services.logger import log


class Worker(Agent):
    def __init__(self, name, system_init, function, config):
        log.info(f"Worker: initializing {name}.")

        self.name: str = name
        self.system_init: Dict[str, str] = system_init
        self.context: List[Dict[str, str]] = [self.system_init]
        self.function: Dict[str, Any] = function
        self.function_call: Dict[str, str] = {"name": function.get("name")}
        self.config: Dict[str, Any] = config

    async def process_request(self, request) -> Dict[str, str] | None:
        log.info(f"Processing request.")

        self.context.append(request)
        state = await self.get_state()
        res = await completion(**state)

        function_call = res.get("function_call")

        if function_call is not None:
            return await self.eval_function_call(res)  # type: ignore

    async def eval_function_call(self, res: dict) -> Dict[str, str] | None:
        log.info("Evaluating worker function call.")

        function_call = res.get("function_call")
        function_name = function_call.get("name")
        function_args = function_call.get("arguments")

        if isinstance(function_args, str):
            function_args = json.loads(function_args)

        if function_name.strip() == self.function.get("name"):
            module_name = f"workers.{function_name}"
            module = importlib.import_module(module_name)
            method_to_call = getattr(module, function_name, None)

            if method_to_call:
                try:
                    return await method_to_call(**function_args)

                except Exception as e:
                    log.error(f"Error during function call: {e}")
            else:
                log.error(f"Function {function_name} not found in {module_name}.")
        else:
            log.error(
                f"Function name mismatch. Expected: {self.function.get('name')}, Received: {function_name}"
            )
