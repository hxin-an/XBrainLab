import argparse
import time
from flask import Flask, request, jsonify
from core.agent import Agent

# Argument Parser
parser = argparse.ArgumentParser()
parser.add_argument("--no_prompt_selection", action="store_true",
                    help="Do not perform semantic prompt selection. Randomly select prompts.")
parser.add_argument("--no_voting", action="store_true",
                    help="Disable multiple inference and majority voting.")
parser.add_argument("--no_rag", action="store_true",
                    help="Disable retrieval-augmented generation.")
args = parser.parse_args()

# Initialize Flask App
app = Flask(__name__)

# Initialize Agent
print("Initializing Agent...")
agent = Agent(
    use_rag=not args.no_rag,
    use_voting=not args.no_voting,
    no_prompt_selection=args.no_prompt_selection
)
print("Agent Ready.")

@app.route('/generate_command', methods=['POST'])
def api_generate_command():
    data = request.get_json()
    input_text = data.get('input_text', '')
    history = data.get('history', '')
    
    print(f"User Input: {input_text}")
    start = time.time()
    
    # Generate Commands
    # We loop/retry in case of empty response if needed, matching original logic
    # Original logic had a while loop with 10s timeout.
    
    commands = []
    while True:
        commands = agent.generate_commands(history, input_text)
        if commands:
            break
        if (time.time() - start) > 10:
            commands = []
            break
            
    print(f"Time elapsed: {time.time()-start:.2f} sec")
    for command in commands:
        print(command)
        
    return jsonify(commands)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)