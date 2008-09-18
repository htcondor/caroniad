%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Summary: Condor EC2 Enhanced hooks
Name: ec2-enhanced-hooks
Version: 1.0
Release: 1%{?dist}
License: ASL 2.0
Group: Applications/System
Source0: %{name}-%{version}.tar.gz
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
Requires: python >= 2.4
Requires: condor >= 7.0.2-4
Requires: condor-job-hooks-common
Requires: ec2-enhanced-hooks-common
Requires: python-boto >= 1.0a

%description
The EC2 Enhanced feature allows for near seamless translation of Condor jobs
in the standard universe to condor EC2 jobs in the grid universe.  For all
intents and purposes, the job runs as any standard universe job runs except
on an Amazon EC2 AMI instance.

This package provides Condor job router hooks that will translate a job into
a Condor EC2 job and monitor the state of that job.  This should be installed
on condor nodes that will submitting work and wish to use the EC2 Enhanced
feature.

%package common
Summary: Common functions/utilties for condor job hooks
Group: Applications/System

%description common
Common functions and utilities used by MRG condor job hooks.

%prep
%setup -q

%install
mkdir -p %{buildroot}/%_var/lib/condor/hooks
mkdir -p %{buildroot}/%{python_sitelib}/ec2enhanced
mkdir -p %{buildroot}/%_sysconfdir/opt/grid
mkdir -p %{_builddir}/%{name}-%{version}/example
cp -f hook*.py %{buildroot}/%_var/lib/condor/hooks
cp -f functions.py %{buildroot}/%{python_sitelib}/ec2enhanced
cp -f config/condor_config.example %{_builddir}/%{name}-%{version}/example
touch %{buildroot}/%{python_sitelib}/ec2enhanced/__init__.py

%files
%defattr(-,root,root,-)
%doc LICENSE-2.0.txt INSTALL example
%defattr(0555,root,root,-)
%_var/lib/condor/hooks/hook_job_finalize.py*
%_var/lib/condor/hooks/hook_translate.py*
%_var/lib/condor/hooks/hook_cleanup.py*
%_var/lib/condor/hooks/hook_retrieve_status.py*

%files common
%{python_sitelib}/ec2enhanced/functions.py*
%{python_sitelib}/ec2enhanced/__init__.py*
