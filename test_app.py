import numpy as np

from streamlit.testing.v1 import AppTest

BOROUGHS = [
    'ALL',
    'BARNET',
    'BARKING & DAGENHAM',
    'BEXLEY',
    'BRENT',
    'BROMLEY',
    'CAMDEN',
    'CITY OF LONDON',
    'CROYDON',
    'EALING',
    'ENFIELD',
    'MERTON',
    'NEWHAM',
    'REDBRIDGE',
    'RICHMOND-UPON-THAMES',
    'SOUTHWARK',
    'SUTTON',
    'TOWER HAMLETS',
    'WALTHAM FOREST',
    'WANDSWORTH',
    'WESTMINSTER',
]

at = AppTest.from_file("app.py", default_timeout=60)

at.run()
print(f"{at.session_state['current_memory_usage']} MB")

c_or_p = at.radio[0].value
for i in range(100):
    if c_or_p  == 'cyclist':
        c_or_p = 'pedestrian'
        at.radio[0].set_value(c_or_p)
    else:
        c_or_p = 'cyclist'
        at.radio[0].set_value(c_or_p)

    n_junctions = int(np.random.randint(1, 100, 1)[0])
    borough = np.random.choice(BOROUGHS)

    print(c_or_p)
    print(f'n_junctions: {n_junctions}')
    print(f'borough: {borough}')

    at.slider[0].set_value(n_junctions)
    at.multiselect[0].select(borough)
    at.button[0].click().run()

    print(f"Current memory usage: {at.session_state['current_memory_usage']} MB")
    print()
