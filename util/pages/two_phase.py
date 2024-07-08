import numpy as np
import plotly.graph_objects as go
from scipy.integrate import odeint
import streamlit as st

# Parameters
A_wake = 9.992750
A_sleep = 7.210033
a12_wake = 0.476125
k = 0.240897
a = 1.01

# Equilibrium points
B_wake = A_wake / a12_wake
B_sleep = A_sleep / (a * a12_wake)
P_wake = A_wake / k
P_sleep = A_sleep / k

# Function to compute the vector field
def model(y, t, state='wake'):
    if state == 'wake':
        A = A_wake
        a12 = a12_wake
    else:
        A = A_sleep
        a12 = a * a12_wake
    
    dydt = np.zeros((2,))
    dydt[0] = A - a12 * y[0]
    dydt[1] = a12 * y[0] - k * y[1]
    return dydt

# Function to plot the phase plane
def plot_phase_plane(y1_range, y2_range, state, y1_label, y2_label, title):
    Y1, Y2 = np.meshgrid(y1_range, y2_range)
    U, V = np.zeros(Y1.shape), np.zeros(Y2.shape)
    
    for i in range(Y1.shape[0]):
        for j in range(Y1.shape[1]):
            y = [Y1[i, j], Y2[i, j]]
            dydt = model(y, 0, state=state)
            U[i, j] = dydt[0]
            V[i, j] = dydt[1]
    
    fig = go.Figure()

    # Add quiver plot for the vector field using Scattergl
    fig.add_trace(go.Scattergl(
        x=Y1.flatten(),
        y=Y2.flatten(),
        mode='markers+lines',
        marker=dict(size=2, color='black'),
        line=dict(width=1),
        name='Vector Field'
    ))

    for i in range(Y1.shape[0]):
        for j in range(Y1.shape[1]):
            fig.add_annotation(
                x=Y1[i, j], y=Y2[i, j],
                ax=Y1[i, j] + U[i, j] * 0.2, ay=Y2[i, j] + V[i, j] * 0.2,
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
                arrowcolor='black'
            )

    # Add title and labels
    fig.update_layout(
        title=title,
        xaxis_title=f'{y1_label} Concentration',
        yaxis_title=f'{y2_label} Concentration',
        showlegend=False
    )

    return fig

# Streamlit App
def two_phase():
    st.title("Interactive Phase Plane Plot")
    
    # Sidebar controls
    state = st.sidebar.radio("State", ('wake', 'sleep'), index=0)
    y1_label = st.sidebar.selectbox("Y1 Axis", ('Brain'))
    y2_label = st.sidebar.selectbox("Y2 Axis", ('Plasma'))

    # User input for axes ranges
    y1_min = st.sidebar.number_input(f"{y1_label} Min", value=-10.0)
    y1_max = st.sidebar.number_input(f"{y1_label} Max", value=20.0)
    y2_min = st.sidebar.number_input(f"{y2_label} Min", value=0.0)
    y2_max = st.sidebar.number_input(f"{y2_label} Max", value=60.0)

    # Range for plotting
    y1_range = np.linspace(y1_min, y1_max, 20)
    y2_range = np.linspace(y2_min, y2_max, 20)
    
    # Plot phase plane
    fig = plot_phase_plane(y1_range, y2_range, state, y1_label, y2_label,
                           f"Phase Plane Plot ({y1_label} vs {y2_label}, {state.capitalize()} State)")
    
    # Click event to show equilibrium point
    click_event = st.plotly_chart(fig, use_container_width=True)
    
    # Handle click event to display the equilibrium point
    if click_event:
        equilibrium_y1 = B_wake if state == 'wake' else B_sleep
        equilibrium_y2 = P_wake if state == 'wake' else P_sleep
        
        fig.add_trace(go.Scatter(
            x=[equilibrium_y1],
            y=[equilibrium_y2],
            mode='markers',
            marker=dict(size=12, color='red' if state == 'wake' else 'blue'),
            name=f'Equilibrium {state.capitalize()}'
        ))
        st.plotly_chart(fig, use_container_width=True)

if __name__ == '__main__':
    two_phase()
