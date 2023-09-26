![LCC logo](img/LCC_logo_horizontal_red.png)

# Automatically Identifying Dangerous Junctions

This project aims to assist the LCC better identify dangerous junctions for both cyclists and pedestrians in London. This is currently a manual process, where junctions are identified using [this tool](https://bikedata.cyclestreets.net/collisions/#9.54/51.5058/-0.1395). The previously identified junctions can be viewed [here](https://lcc.org.uk/campaigns/dangerous-junctions/).

The aim of this project is to use the [open source TfL collision data](https://tfl.gov.uk/corporate/publications-and-reports/road-safety) to do this automatically. This is not a trivial problem since the collisions in the data are not tied to an identifiable junction name or code. Instead they are recorded using coordinates, which may vary even for collisisons at the same junction. So the challenge is being able to link together collisions that happen at the same junction so that we can create some kind of danger metric at each junction.

The junctions identified via this 'automatic' approach can be viewed in this [interactive app](https://lcc-dangerous-junctions.streamlit.app/). For more details on the approach, see section below.

## The Approach

The current method used to identify dangerous junctions works as follows:

1. Pull TfL data for the last 5 years, filter to collisions involving either a cyclist or pedestrian
2. Generate junctions network for London, generated using the [OSMnx](https://github.com/gboeing/osmnx/tree/main). See example below for the junction network for Trafalgar Square.

![Junctions pre consolidation](img/junctions-pre-consolidation.png)

3. Consolidate the junctions so those very close together are combined. For example we don't want every set of traffic lights on Trafalgar Square roundabout to be included as separate junctions. See example below of the junction network after the junctions have been combined:

![Junctions post consolidation](img/junctions-post-consolidation.png)

4. Map collisions to the nearest junction.

*__TODO__ - update this with new approach*

The current method used to identify dangerous junctions works as follows:
1. Filter to only 'severe' and 'fatal' collisions
2. Weight collisions so more recent and severe ones are upweighted:
    - If 'fatal': 3 * log(year - 1998)
    - If 'serious': log(year - 1998)
    
![recency weight plot](plots/recency-weight.png)

3. Cluster the collisions together using the DBSCAN clustering algorithm

![junctions](plots/junctions.png)

4. Aggregate the collision weights at each junction to get a 'danger rank'

![ranked junctions](plots/ranked-junctions.png)

The main notebooks to follow for the above are:
- [dft-collision-data.ipynb](https://github.com/danielhills/lcc-dangerous-junctions/blob/main/notebooks/dft-collision-data.ipynb)
- [clustering-collisions.ipynb](https://github.com/danielhills/lcc-dangerous-junctions/blob/main/notebooks/clustering-collisions.ipynb) (probably won't render on GitHub)

An interactive app with junctions identified with this approach is [here](https://lcc-dangerous-junctions.streamlit.app/).

## Using this code

To run and develop on this code:
- Clone the repo
- Make sure Python installed
- Setup a virtual environment, e.g: ```python3 -m venv venv```
- Activate the virtual environment: `source venv/bin/activate`
- Install the packages using: `pip install -r requirements.txt`
- Run the following:
    - `python src/01-download-tfl-data.py` file to download and format the TfL data
    - `python src/02-filter-data.py` to filter the data to London etc.
    - `python src/03-build-junctions-graph.py` to build junctions graph for London
    - `python src/04-map-collisions-to-graph.py` to map collision data to the closest junction in the London junction graph

You should now be setup to run the notebooks in `notebooks/` and the streamlit app. The streamlit app locally can be done using: `streamlit run app.py` and navigating to the local host port.

## References

- [OSMnx](https://github.com/gboeing/osmnx/tree/main) - this package was used to generate the junction network for London, which the collisions are mapped to. Original paper:
> Boeing, G. 2017. "OSMnx: New Methods for Acquiring, Constructing, Analyzing, and Visualizing Complex Street Networks." Computers, Environment and Urban Systems 65, 126-139.

- Collision data is taken from TfL's "Collision data extracts" that can be accessed [here](https://tfl.gov.uk/corporate/publications-and-reports/road-safety)
