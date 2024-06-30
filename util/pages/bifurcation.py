import streamlit as st
import sympy as sp
import numpy as np
import matplotlib.pyplot as plt

# Initialize session state variables
if 'equations_input' not in st.session_state:
    st.session_state.equations_input = ""
if 'equilibrium_points' not in st.session_state:
    st.session_state.equilibrium_points = None
if 'parameters' not in st.session_state:
    st.session_state.parameters = []
if 'variable_parameter' not in st.session_state:
    st.session_state.variable_parameter = None

def find_parameters(equations, variables):
    sym_vars = sp.symbols(variables)
    sym_eqns = [sp.sympify(eq.split('=')[1].strip()) for eq in equations]
    parameters = set()
    for eq in sym_eqns:
        parameters.update(str(symbol) for symbol in eq.free_symbols if symbol not in sym_vars)
    return list(parameters)

def find_equilibrium(equations, variables):
    sym_vars = sp.symbols(variables)
    sym_eqns = [sp.sympify(eq.split('=')[1].strip()) for eq in equations]
    eqns_at_equilibrium = [sp.Eq(eq, 0) for eq in sym_eqns]
    try:
        equilibrium_points = sp.solve(eqns_at_equilibrium, sym_vars, dict=True)
        return equilibrium_points
    except Exception as e:
        st.error(f"Error solving equilibrium points: {str(e)}")
        return []

def plot_bifurcation(variable, expression, variable_param, param_range, constant_params):
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x_values = param_range
    y_values = []
    
    for x in x_values:
        subs_dict = {variable_param: x, **constant_params}
        y = expression.subs(subs_dict)
        y_values.append(float(y))
    
    ax.plot(x_values, y_values, marker='o')
    ax.set_xlabel(variable_param)
    ax.set_ylabel(f"{variable}*")
    ax.set_title(f"Bifurcation diagram: {variable}* vs {variable_param}")
    st.pyplot(fig)

def bifurcation_page():
    st.title("Equilibrium Points Calculator and Bifurcation Plotter for ODEs")
    st.write("Enter your system of differential equations in the format 'dX/dt = ...' for each equation. Use a new line for each equation.")

    equations_input = st.text_area("Enter the differential equations:", height=200, value=st.session_state.equations_input)
    
    if st.button("Calculate Equilibrium Points"):
        st.session_state.equations_input = equations_input
        equations_list = [eq.strip() for eq in equations_input.split('\n') if eq.strip()]
        variables_set = set(eq.split('=')[0].strip().split('/')[0][1:] for eq in equations_list)
        variables_list = list(variables_set)

        try:
            st.session_state.parameters = find_parameters(equations_list, variables_list)
            st.session_state.equilibrium_points = find_equilibrium(equations_list, variables_list)
            
            if st.session_state.equilibrium_points:
                st.write("The equilibrium points for the given set of equations are:")
                for point in st.session_state.equilibrium_points:
                    for var, expr in point.items():
                        st.latex(f"{sp.latex(var)}^* = {sp.latex(expr)}")
            else:
                st.warning("No equilibrium points found.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    if st.session_state.equilibrium_points:
        st.write("\nNow, let's plot the bifurcation diagram.")
        
        variable_param = st.selectbox("Select the parameter to vary:", st.session_state.parameters, key="variable_param")
        st.session_state.variable_parameter = variable_param
        
        constant_params = {}
        for param in st.session_state.parameters:
            if param != variable_param:
                constant_params[param] = st.number_input(f"Value for {param}:", value=1.0, key=f"const_{param}")
        
        lower_limit = st.number_input(f"Lower limit for {variable_param}:", value=0.1)
        upper_limit = st.number_input(f"Upper limit for {variable_param}:", value=10.0)
        num_points = st.number_input("Number of points:", value=100, min_value=10, max_value=1000, step=10)
        
        if st.button("Plot Bifurcation Diagram"):
            param_range = np.linspace(lower_limit, upper_limit, num_points)
            
            for point in st.session_state.equilibrium_points:
                for var, expr in point.items():
                    plot_bifurcation(var, expr, variable_param, param_range, constant_params)

if __name__ == '__main__':
    bifurcation_page()
