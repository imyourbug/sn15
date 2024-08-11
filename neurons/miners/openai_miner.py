# The MIT License (MIT)
# Copyright © 2024 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import os
import time
import bittensor as bt
import argparse

# Bittensor Miner Template:
from deval.protocol import EvalSynapse
from deval.tasks import TasksEnum
import re

# import base miner class which takes care of most of the boilerplate
from deval.base.eval_miner import Miner
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI 
from neurons.miners.prompts import (
    format_prompt,
    RELEVANCY_PROMPT, 
    HALLUCINATION_PROMPT, 
    ATTRIBUTION_PROMPT, 
    SUMMARY_COMPLETENESS_PROMPT
)


class OpenAIMiner(Miner):
    """Langchain-based miner which uses OpenAI's API as the LLM.

    You should also install the dependencies for this miner, which can be found in the requirements.txt file in this directory.
    """

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser):
        """
        Adds OpenAI-specific arguments to the command line parser.
        """
        super().add_args(parser)

    def __init__(self, config=None):
        super().__init__(config=config)

        bt.logging.info(f"Initializing with model {self.config.neuron.model_id}...")

        self.set_parameters()

        _ = load_dotenv(find_dotenv())
        API_KEY = os.environ.get("OPENAI_API_KEY")

        # Set openai key and other args
        self.model = OpenAI(api_key=API_KEY)

        self.system_prompt = "You are LLM evaluator. Your goal is to respond to the evaluation question with a score between 0 and 1, where 1 signifies fully accurate and 0 signifies completely inaccurate."
        

    def set_parameters(self) -> None:
        self.model_id = self.config.neuron.model_id

        self.max_tokens = self.config.neuron.max_tokens or 10
        self.temperature = self.config.neuron.temperature or 0.5
        self.top_p = self.config.neuron.top_p or 0.95
        self.top_k = self.config.neuron.top_k or 0

    def select_task_prompt(self, task: str) -> str:
        if task == TasksEnum.ATTRIBUTION.value:
            return ATTRIBUTION_PROMPT
        elif task == TasksEnum.COMPLETENESS.value:
            return SUMMARY_COMPLETENESS_PROMPT
        elif task == TasksEnum.HALLUCINATION.value:
            return HALLUCINATION_PROMPT
        elif task == TasksEnum.RELEVANCY.value:
            return RELEVANCY_PROMPT
        else:
            bt.logging.error("Unable to identify the task")
            raise ValueError(f"Unable to find the correct task: {task}")

    def parse_response(self, response: str) -> float:
        float_regex = "((0\.\d+?|1\.0+?|0|1|\.\d+))"
        match = re.search(f"response: {float_regex}", response.lower())
        if match:
            score = match.group(1)
            print("score ", score)
            return float(score.strip()) if score != "" else -1.0
        else:
            bt.logging.debug("Unable to parse response")
            return -1.0



    async def forward(self, synapse: EvalSynapse) -> EvalSynapse:
        """
        Processes the incoming synapse by performing a predefined operation on the input data.
        This method should be replaced with actual logic relevant to the miner's purpose.

        Args:
            synapse (EvalSynapse): The synapse object containing the 'dummy_input' data.

        Returns:
            EvalSynapse: The synapse object with the 'dummy_output' field set to twice the 'dummy_input' value.

        The 'forward' function is a placeholder and should be overridden with logic that is appropriate for
        the miner's intended operation. This method demonstrates a basic transformation of input data.
        """
        try:
            t0 = time.time()
            bt.logging.debug(f"📧 Message received, forwarding synapse: {synapse}")

            task = synapse.tasks[0]
            rag_context = synapse.rag_context
            query = synapse.query
            llm_response = synapse.llm_response

            # generate our prompt and format
            prompt = self.select_task_prompt(task)
            prompt = format_prompt(prompt, rag_context=rag_context, query=query, llm_response=llm_response)
            messages = [{"content": prompt, "role": "user"}]
            

            # generate our response and return
            output = self.model.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature = self.temperature,
                top_p = self.top_p,
                max_tokens = self.max_tokens,
            )
            response = output.choices[0].message.content
            completion = self.parse_response(response)
            bt.logging.info(f"completion: {completion}")
            synapse.completion = completion

            synapse_latency = time.time() - t0

            
            bt.logging.info(f"✅ Served Response: {response}, with latency: {synapse_latency}")

            return synapse
        except Exception as e:
            bt.logging.error(f"Error in forward: {e}")
            synapse.completion = -1.0
        finally:
            if self.config.neuron.stop_on_forward_exception:
                self.should_exit = True
            return synapse


# This is the main function, which runs the miner.
if __name__ == "__main__":
    with OpenAIMiner() as miner:
        while True:
            miner.log_status()
            time.sleep(5)

            if miner.should_exit:
                bt.logging.warning("Ending miner...")
                break