# LCC - Automatically Identifying Dangerous Junctions

This is a volunteer project aiming to help LCC better identify dangerous junctions for both cyclists and pedestrians in London. This is currently a manual process, where junctions are identified using [this tool](https://bikedata.cyclestreets.net/collisions/#9.54/51.5058/-0.1395). The currently identified junctions can be viewed [here](https://lcc.org.uk/campaigns/dangerous-junctions/).

The aim of this project is to use the [open source DfT collision data](https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data) to do this automatically. This is not a trivial problem since the collisions in the data are not tied to an identifiable junction name or code. Instead they are recorded using coordinates, which may vary even for collisison at the same junction. So the challenge is being able to link together collisions that happen at the same junction so that we can create some kind of danger metric at each junction.

I'm hoping to recreate and extend this work, see research so far in: `notebooks/`

See app with junctions identified with this approach [here](https://danielhills-lcc-dangerous-junctions-app-b63snl.streamlitapp.com/).

## Running

To run and develop on this code:
- Clone the repo
- Setup a virtual environment, e.g. `python3 -m venv venv`
- Activate the virtual environment, `source/venv/activate`
- Install the packages using `pip install -r requirements.txt`

__TODO:__ host the processed collision data somewhere

Running the streamlit app locally can be done using: `streamlit run app.py` and navigating to the local host port.