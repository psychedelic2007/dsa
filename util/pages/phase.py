import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import odeint
import streamlit as st

# Parameters
A = 12.063
sigma_A = 0.782
r_bc = 1.623
sigma_bc = 2.505
r_cp = 0.00572
sigma_cp = 5.190
r_bp = 0.199
sigma_bp = 4.618
r_p = 0.300
sigma_p = 4.670

# Equilibrium points
B_wake = A / (r_bc+r_bp)
B_sleep = (sigma_A * A)/ (sigma_bc*r_bc + sigma_bp*r_bp)
C_wake = (r_bc * A) / (r_cp * (r_bc+r_bp))
C_sleep = (sigma_bc*r_bc * sigma_A*A) / (sigma_cp*r_cp * (sigma_bc*r_bc+sigma_bp*r_bp))
P_wake = A / r_p
P_sleep = (sigma_A*A) / (sigma_p*r_p)

# Function to compute the vector field
def model(y, t, state='wake'):
    if state == 'wake':
        A = A
        a12 = r_bc
        a13 = r_bp
        a23 = r_cp
        k = r_p
    else:
        A = sigma_A*A
        a12 = sigma_bc*r_bc
        a13 = sigma_bp*r_bp
        a23 = sigma_cp*r_cp
        k = sigma_p*r_p
    
    dydt = np.zeros((3,))
    dydt[0] = A - (a13 + a12) * y[0]
    dydt[1] = a12 * y[0] - a23 * y[1]
    dydt[2] = a23 * y[1] + a13 * y[0] - k * y[2]
    return dydt

# Function to plot the phase plane
def plot_phase_plane(y1_range, y2_range, state, y1_label, y2_label, equilibrium_y1, equilibrium_y2, title):
    Y1, Y2 = np.meshgrid(y1_range, y2_range)
    U, V = np.zeros(Y1.shape), np.zeros(Y2.shape)
    
    for i in range(Y1.shape[0]):
        for j in range(Y1.shape[1]):
            if y1_label == 'Brain':
                y = [Y1[i, j], 0, Y2[i, j]] if y2_label == 'Plasma' else [Y1[i, j], Y2[i, j], 0]
            elif y1_label == 'CSF':
                y = [0, Y1[i, j], Y2[i, j]]
            dydt = model(y, 0, state=state)
            U[i, j] = dydt[0] if y1_label == 'Brain' else dydt[1]
            V[i, j] = dydt[2] if y2_label == 'Plasma' else dydt[1]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.quiver(Y1, Y2, U, V, width=0.002, color='r' if state == 'wake' else 'b')
    ax.set_title(title)
    ax.set_xlabel(f'{y1_label} Concentration')
    ax.set_ylabel(f'{y2_label} Concentration')
    ax.legend()
    
    return fig

# Streamlit App
def main():
    st.title("Interactive Phase Plane Plot")
    
    # Sidebar controls
    state = st.sidebar.radio("State", ('wake', 'sleep'), index=0)
    y1_label = st.sidebar.selectbox("Y1 Axis", ('Brain', 'CSF'))
    y2_label = st.sidebar.selectbox("Y2 Axis", ('CSF', 'Plasma'))

    # User input for axes ranges
    y1_min = st.sidebar.number_input(f"{y1_label} Min", value=-10.0)
    y1_max = st.sidebar.number_input(f"{y1_label} Max", value=20.0)
    y2_min = st.sidebar.number_input(f"{y2_label} Min", value=-10.0 if y2_label == 'CSF' else 0.0)
    y2_max = st.sidebar.number_input(f"{y2_label} Max", value=60.0)

    # Range for plotting
    y1_range = np.linspace(y1_min, y1_max, 20)
    y2_range = np.linspace(y2_min, y2_max, 20)
    
    # Plot phase plane
    fig = plot_phase_plane(y1_range, y2_range, state, y1_label, y2_label,
                           B_wake if state == 'wake' else B_sleep, C_wake if state == 'wake' else C_sleep,
                           f"Phase Plane Plot ({y1_label} vs {y2_label}, {state.capitalize()} State)")
    
    st.pyplot(fig)
    
if __name__ == '__main__':
    main()

