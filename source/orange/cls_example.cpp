/*
    This file is part of Orange.

    Orange is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    Orange is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Orange; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

    Authors: Janez Demsar, Blaz Zupan, 1996--2002
    Contact: janez.demsar@fri.uni-lj.si
*/


#include "stladdon.hpp"
#include "orange.hpp"

class TMLClassDefinition;
extern TMLClassDefinition MLDef_Domain;
extern TMLClassDefinition MLDef_Variable;

#include "vars.hpp"
#include "domain.hpp"
#include "examples.hpp"

#include "cls_value.hpp"
#include "cls_example.hpp"
#include "cls_orange.hpp"
#include "lib_kernel.hpp"
#include "converts.hpp"

#include "externs.px"


DATASTRUCTURE(Example, TPyExample, 0)


bool convertFromPythonExisting(PyObject *lst, TExample &example)
{
  PDomain dom=example.domain;

  if (!PyList_Check(lst)) {
    PyErr_Format(PyExc_TypeError, "invalid argument type (expected list, got '%s)", lst ? lst->ob_type->tp_name : "None");
    return false;
  }

  if (int(dom->variables->size()) != PyList_Size(lst)) {
    PyErr_Format(PyExc_IndexError, "invalid list size (%i items expected)", dom->variables->size());
    return false;
  }

  int pos=0;
  TExample::iterator ei(example.begin());
  PITERATE(TVarList, vi, dom->variables) {
    PyObject *li=PyList_GetItem(lst, pos++);
    if (!li)
      PYERROR(PyExc_SystemError, "can't read the list", false);

    if (PyOrValue_Check(li))
      if (PyValue_AS_Variable(li) ? (PyValue_AS_Variable(li) != *vi) : (PyValue_AS_Value(li).varType=!(*vi)->varType) ) {
        PyErr_Format(PyExc_TypeError, "wrong value type for attribute no. %i (%s)", pos, (*vi)->name.c_str());
        return false;
      }
      else
        *(ei++)=PyValue_AS_Value(li);

    else {
      if (PyString_Check(li))
          (*vi)->str2val(string(PyString_AsString(li)), *(ei++));

      else if ((*vi)->varType==TValue::INTVAR) {
        if (PyInt_Check(li))
          *(ei++)=TValue(int(PyInt_AsLong(li)));
        else {
          PyErr_Format(PyExc_TypeError, "attribute no. %i (%s) is ordinal, string value expected", pos, (*vi)->name.c_str());
          return false;
        }
      }
      else if ((*vi)->varType==TValue::FLOATVAR) {
        if (PyNumber_Check(li)) 
          *(ei++)=TValue(PyNumber_AsFloat(li));
        else {
          PyErr_Format(PyExc_TypeError, "attribute no. %i (%s) is continuous, float value expected", pos, (*vi)->name.c_str());
          return false;
        }
      }
      else
        ei++;
    }
  }

  return true;
}


bool convertFromPython(PyObject *lst, TExample &example, PDomain dom)
{ example=TExample(dom);
  return convertFromPythonExisting(lst, example);
}


PyObject *Example_FromExample(PyTypeObject *type, PExample example, POrange lock)
{ TPyExample *self=PyObject_GC_New(TPyExample, type);
  self->example.init();
  self->lock.init();
  self->example = example;
  self->lock = lock;
  PyObject_GC_Track(self);
  return (PyObject *)self;
}


void Example_dealloc(TPyExample *self)
{ self->lock.~POrange();
  self->example.~PExample();
  /* Should not call tp_free if it is a reference 
     Destructor is also called by exit proc, not by wrapped */
  if (PyObject_IsPointer(self)) {
    PyObject_GC_UnTrack((PyObject *)self);
    self->ob_type->tp_free((PyObject *)self); 
  }
}


int Example_traverse(TPyExample *self, visitproc visit, void *arg)
{ PVISIT(self->lock)
  if (!self->lock) // don't visit if it's a reference!
    PVISIT(self->example);

  return 0;
}

int Example_clear(TPyExample *self)
{ self->lock=POrange();
  self->example=PExample();
  return 0;
}


PyObject *Example_new(PyTypeObject *type, PyObject *args, PyObject *) BASED_ON(ROOT, "(domain, [list of values])")
{ PyTRY
    PyObject *list=PYNULL;
    PDomain dom;

    if (!PyArg_ParseTuple(args, "O&|O", cc_Domain, &dom, &list))
      PYERROR(PyExc_TypeError, "domain and (optionally) list arguments accepted", PYNULL);

    if (list && PyOrExample_Check(list)) {
      PExample ex = mlnew TExample(dom, PyExample_AS_Example(list).getReference());
      return Example_FromWrappedExample(ex);
    }

    PyObject *example = Example_FromDomain(dom);
    if (list && !convertFromPythonExisting(list, PyExample_AS_ExampleReference(example))) {
      Example_dealloc((TPyExample *)example);
      return PYNULL;
    }
      
    return example;
  PyCATCH
}



int getMetaIdFromPy(PExample example, PyObject *index, PVariable &var)
{ if (PyInt_Check(index)) {
    int idx=PyInt_AsLong(index);
    var=example->domain->getMetaVar(idx, false); // it may also be NULL
    return idx;
  }
  else if (PyString_Check(index)) {
    TMetaDescriptor const *desc=example->domain->metas[PyString_AsString(index)];
    if (!desc) {
      PyErr_Format(PyExc_IndexError, "invalid meta variable name '%s'", PyString_AsString(index));
      return 0;
    }
    var=desc->variable;
    return desc->id;
  }
  else if (PyOrVariable_Check(index)) {
    var = PyOrange_AsVariable(index);
    int idx = example->domain->getMetaNum(var, false);
    if (idx==-1)
      PYERROR(PyExc_IndexError, "invalid meta variable", 0);
    return idx;
  }

  PYERROR(PyExc_IndexError, "invalid meta variable", 0);
}


PyObject *Example_getweight(TPyExample *pex, PyObject *pyindex) PYARGS(METH_O, "(id) -> weight; Returns example's weight")
{ PyTRY
    if (!PyInt_Check(pyindex))
      PYERROR(PyExc_TypeError, "an integer id expected", PYNULL);

    int index = (int)PyInt_AsLong(pyindex);

    if (!index)
      return PyFloat_FromDouble(1.0);

    TValue val = PyExample_AS_Example(pex)->meta[index];

    if (val.isSpecial() || (val.varType!=TValue::FLOATVAR))
      PYERROR(PyExc_TypeError, "invalid weight", PYNULL);

    return PyFloat_FromDouble((double)val.floatV);
  PyCATCH
}


PyObject *Example_setweight(TPyExample *pex, PyObject *args) PYARGS(METH_VARARGS, "(id[, weight]); Sets example's weight to given value")
{ PyTRY
    int index;
    float weight = 1;

    if (!PyArg_ParseTuple(args, "if:setweight", &index, &weight))
      return PYNULL;
    if (index<=0)
      PYERROR(PyExc_IndexError, "Example.setweight: invalid weight id", PYNULL);      

    PyExample_AS_Example(pex)->meta.setValue(index, TValue(weight));

    RETURN_NONE;
  PyCATCH
}


PyObject *Example_removeweight(TPyExample *pex, PyObject *pyindex) PYARGS(METH_O, "(id); Removes examples's weight")
{ PyTRY
    if (!PyInt_Check(pyindex))
      PYERROR(PyExc_TypeError, "an integer id expected", PYNULL);

    int index = (int)PyInt_AsLong(pyindex);

    if (index<=0)
      PYERROR(PyExc_IndexError, "Example.setweight: invalid weight id", PYNULL);      

    PyExample_AS_Example(pex)->meta.removeValue(index);
    RETURN_NONE;
  PyCATCH
}


PyObject *Example_getmeta(TPyExample *pex, PyObject *index) PYARGS(METH_O, "(id | var) -> Value; Gets a meta-value")
{ PyTRY
    PVariable var;
    int idx = getMetaIdFromPy(PyExample_AS_Example(pex), index, var);
    if (!idx)
      return PYNULL; 

    return convertToPythonNative(PyExample_AS_Example(pex)->meta[idx], var);
  PyCATCH
}


PyObject *Example_setmeta(TPyExample *pex, PyObject *args) PYARGS(METH_VARARGS, "(Value, int) | (variable, value); Sets a meta-value")
{ PyTRY
    PExample example=PyExample_AS_Example(pex);
  
    PyObject *par1, *par2=PYNULL;
    if (!PyArg_ParseTuple(args, "O|O", &par1, &par2))
      PYERROR(PyExc_TypeError, "invalid arguments", PYNULL);

    int idx=0;

    if (PyOrValue_Check(par1)) {
      // first parameter is a PyValue
      // second parameter is an index and is accepted iff variable not among domain's meta variables
      TMetaDescriptor *desc=PyValue_AS_Variable(par1) ? example->domain->metas[PyValue_AS_Variable(par1)] : (TMetaDescriptor *)NULL;
      if (desc) 
        if (par2)
          PYERROR(PyExc_TypeError, "second argument (index) not expected", PYNULL)
        else
          idx=desc->id;
      else
       if (!par2)
         PYERROR(PyExc_TypeError, "second argument (index) needed", PYNULL)
       else
         if (!PyInt_Check(par2))
           PYERROR(PyExc_TypeError, "invalid index type (int expected)", PYNULL)
         else 
           idx=int(PyInt_AsLong(par2));

      example->meta.setValue(idx, PyValue_AS_Value(par1));
    }

    else if (!par2)
      PYERROR(PyExc_TypeError, "invalid arguments (second argument missing or the first is of wrong type)", PYNULL)

    else if (PyOrVariable_Check(par1) || PyString_Check(par1) || PyInt_Check(par1)) {
      // first parameter will denote the variable, the second the value
      int idx;
      PVariable var;

      if (PyInt_Check(par1)) {
        idx=PyInt_AsLong(par1);
        TMetaDescriptor *desc=example->domain->metas[idx];
        if (desc)
          var=desc->variable;
        else {
          PyErr_Format(PyExc_TypeError, "invalid id (%i)", idx);
          return PYNULL;
        }
      }

      else {
        TMetaDescriptor *desc=example->domain->metas[
            PyOrVariable_Check(par1) ? PyOrange_AS(TVariable, par1).name
                                     : string(PyString_AsString(par1))];
        if (!desc)
          PYERROR(PyExc_TypeError, "invalid variable", PYNULL);
        idx=desc->id;
        var=desc->variable;
      }

      TValue val;
      if (!convertFromPython(par2, val, var))
        return PYNULL;
      example->meta.setValue(idx, val);
    }

    else
      PYERROR(PyExc_TypeError, "invalid arguments", PYNULL)

    RETURN_NONE;
  PyCATCH
}
  

PyObject *Example_removemeta(TPyExample *pex, PyObject *index) PYARGS(METH_O, "(id); Removes a meta-value")
{ PyTRY
    PVariable var;
    int idx = getMetaIdFromPy(PyExample_AS_Example(pex), index, var);
    if (!idx)
      return PYNULL; 

    PyExample_AS_Example(pex)->meta.removeValue(idx);
    RETURN_NONE;
  PyCATCH
}



PyObject *Example_getclass(TPyExample *pex) PYARGS(METH_NOARGS, "()  -> Value; Returns example's class")
{ PyTRY
      const TExample &example = PyExample_AS_ExampleReference(pex);
      const PVariable &classVar = example.domain->classVar;

      if (!classVar)
        raiseError("class-less domain");

      return Value_FromVariableValue(classVar, example.getClass());
  PyCATCH
}


PyObject *Example_setclass(TPyExample *pex, PyObject *val) PYARGS(METH_O, "(value); Sets example's class")
{ PyTRY
    PExample &example=PyExample_AS_Example(pex);
    PVariable &classVar = example->domain->classVar;

    if (!classVar)
      PYERROR(PyExc_SystemError, "classless domain", PYNULL);

    TValue value;
    if (!convertFromPython(val, value, classVar)) 
      return PYNULL;
    example->setClass(value);

    RETURN_NONE;
  PyCATCH
}



PyObject *Example_compatible(TPyExample *pex, PyObject *obj) PYARGS(METH_O, "(example); Returns true if examples are compatible")
{ PyTRY
    if (!PyOrExample_Check(obj))
      PYERROR(PyExc_TypeError, "example expected", PYNULL)
    else
      return PyInt_FromLong(PyExample_AS_Example(pex)->compatible(PyExample_AS_ExampleReference(obj)) ? 1 : 0);
  PyCATCH
}


int getAttributeIndex(PDomain domain, PyObject *vara)
{
    if (PyInt_Check(vara)) {
      int ind = int(PyInt_AsLong(vara));
      if (ind<0)
        ind += domain->variables->size();
      if ((ind<0) || (ind>=int(domain->variables->size()))) {
        PyErr_Format(PyExc_IndexError, "index %i out of range 0-%i", ind, domain->variables->size()-1);
        return -1;
      }
      return ind;
    }

    PVariable var=varFromArg_byDomain(vara, domain);
    if (!var) 
      PYERROR(PyExc_TypeError, "invalid arguments or unknown attribute name", -1);

    return domain->getVarNum(var);
}


PyObject *Example_getitem(TPyExample *pex, PyObject *vara)
{ PyTRY
    PExample example = PyExample_AS_Example(pex);
    int ind = getAttributeIndex(example->domain, vara);
    if (ind<0)
      return PYNULL;

    return Value_FromVariableValue(example->domain->variables->at(ind), example->operator[](ind));
  PyCATCH
}


int exampleIndex(PExample example, int ind)
{ 
  int attrs = example->domain->variables->size();
  if (ind<0)
    ind += attrs;
  if ((ind<0) || (ind>=int(example->domain->variables->size()))) {
    PyErr_Format(PyExc_IndexError, "index %i out of range 0-%i", ind, attrs-1);
    return -1;
  }
  return ind;
}


PyObject *Example_getitem_sq(TPyExample *pex, int idx)
{ PyTRY
    PExample example=PyExample_AS_Example(pex);
    int ind=exampleIndex(example, idx);
    if (ind<0)
      return PYNULL;

    return Value_FromVariableValue(example->domain->variables->at(ind), example->operator[](ind));
  PyCATCH
}


int TPyExample_setItem_lower(PExample example, const int &ind, PyObject *vala)
{  PyTRY
      if (ind<0)
      return -1;

    PVariable var=example->domain->variables->at(ind);

    if (PyOrValue_Check(vala)) {
      if (PyValue_AS_Variable(vala) && (PyValue_AS_Variable(vala)!=var)) {
          string vals;
          PyValue_AS_Variable(vala)->val2str(PyValue_AS_Value(vala), vals);
          var->str2val(vals, example->operator[](example->domain->getVarNum(var)));
        }
        else
          example->operator[](example->domain->getVarNum(var))=PyValue_AS_Value(vala);
    }

    else {
      TValue value;
      if (!convertFromPython(vala, value, var)) 
        return -1;
      example->operator[](example->domain->getVarNum(var))=value;
    }

    return 0;
  PyCATCH_1
}


int Example_setitem(TPyExample *pex, PyObject *vara, PyObject *vala)
{ PyTRY
    PExample example=PyExample_AS_Example(pex);
    return TPyExample_setItem_lower(example, getAttributeIndex(example->domain, vara), vala);
  PyCATCH_1
}


int Example_setitem_sq(TPyExample *pex, const int &ind, PyObject *vala)
{ PyTRY
    PExample example=PyExample_AS_Example(pex);
    return TPyExample_setItem_lower(example, exampleIndex(example, ind), vala);
  PyCATCH_1
}



PyObject *toValue(const TValue &val, PVariable var, int natvt)
{ switch (natvt) {
    case -1: return (val.varType==TValue::INTVAR)
               ? PyInt_FromLong(long(val.intV))
               : PyFloat_FromDouble(double(val.floatV));
    case  0: return convertToPythonNative(val, var);
    default: return Value_FromVariableValue(var, val);
  }
}

PyObject *convertToPythonNative(const TExample &example, int natvt, bool tuples)
{
  PyObject *list=PyList_New(0);
  TExample::const_iterator ei=example.begin();
  const_PITERATE(TVarList, vi, example.domain->attributes)
    PyList_Append(list, toValue(*(ei++), *vi, natvt));

  PyObject *pyclass=toValue(example.getClass(), example.domain->classVar, natvt);

  if (tuples)
    return Py_BuildValue("NN", list, pyclass);
  else {
    PyList_Append(list, pyclass);
    return list;
  }
}


PyObject *Example_native(TPyExample *pex, PyObject *args, PyObject *keyws) PYARGS(METH_VARARGS | METH_KEYWORDS, "([nativity])  -> list; Converts an example to a list")
{ PyTRY
    int natvt=1;
    if (args && !PyArg_ParseTuple(args, "|i", &natvt))
      PYERROR(PyExc_TypeError, "invalid arguments (no arguments or an integer expected)", PYNULL);

    bool tuples=false;
    if (NOT_EMPTY(keyws))
      if ((PyDict_Size(keyws)==1)) {
         PyObject *pytuples = PyDict_GetItemString(keyws, "tuple");
         tuples = pytuples && (PyInt_AsLong(pytuples)!=0);
       }
      else 
        PYERROR(PyExc_TypeError, "invalid arguments", PYNULL);

    return convertToPythonNative(PyExample_AS_ExampleReference(pex), natvt, tuples);
  PyCATCH
}



inline void addValue(string &res, const TValue &val, PVariable var)
{ string str;
  var->val2str(val, str);
  if (var->varType!=TValue::FLOATVAR) res+="'"+str+"'";
  else res+=str;
}

string TPyExample2string(TPyExample *pex)
{ PExample example=PyExample_AS_Example(pex);
  string res("[");
  TVarList::iterator vi(example->domain->variables->begin());
  PITERATE(TExample, ei, example) {
    if (ei!=example->begin())
      res+=", ";
    addValue(res, *ei, *(vi++));
  }
  res+="]";

  int madded=0;
  ITERATE(TMetaValues, mi, example->meta) {
    res+= (madded++) ? ", " : ", {";
    
    TMetaDescriptor *desc=example->domain->metas[(*mi).first];
    if (desc) {
      res+="\""+desc->variable->name+"\":";
      addValue(res, (*mi).second, desc->variable);
    }
    else
      if ((*mi).second.varType==TValue::FLOATVAR) {
        char buf[128];
        sprintf(buf, "%i:%.2f", int((*mi).first), (*mi).second.floatV);
        res += buf;
      }
      else
        res+="???";
  }

  if (madded) res+="}";

  return res;
}

PyObject *Example_repr(TPyExample *pex)
{ PyTRY
    return PyString_FromString(TPyExample2string(pex).c_str()); 
  PyCATCH
}

PyObject *Example_str(TPyExample *pex)
{ PyTRY
    return PyString_FromString(TPyExample2string(pex).c_str()); 
  PyCATCH
}

PyObject *Example_get_domain(TPyExample *self)
{ PyTRY
    return WrapOrange(PyExample_AS_Example(self)->domain);
  PyCATCH
}

int Example_cmp(TPyExample *one, TPyExample *another)
{ PyTRY
    return PyExample_AS_Example(one)->compare(PyExample_AS_ExampleReference(another));
  PyCATCH_1
}


int Example_len(TPyExample *pex)
{ PyTRY
    return PyExample_AS_Example(pex)->domain->variables->size();
  PyCATCH_1
}


#include "cls_example.px"
